"""AudioEngineの入力側/出力側コールバック・ジッタバッファ・ストリーム開始失敗時の
後始末を検証する(D-009: 単一sd.Streamから独立したInputStream/OutputStream+
リングバッファ構成への変更に伴う書き直し)。

実際のsounddeviceストリーム(実オーディオデバイス)はこの環境では扱えないため、
`AudioEngine._input_callback`/`_output_callback`をPortAudioを介さず直接呼び出して
検証する。ストリーム開始の検証は`sd.InputStream`/`sd.OutputStream`をフェイクに
差し替えて行う。
"""

from __future__ import annotations

import numpy as np
import pytest

from soloclarity.audio import engine as engine_mod
from soloclarity.audio.engine import JITTER_BUFFER_FRAMES, PRIME_TARGET_FRAMES, AudioEngine
from soloclarity.dsp.chain import FRAME_SIZE


class _FailingChain:
    def process(self, frame):
        raise ValueError("boom")


class _PassthroughChain:
    def process(self, frame):
        return frame * 2.0, 1.0


def _in_frame(value: float) -> np.ndarray:
    return np.ones((FRAME_SIZE, 1), dtype=np.float32) * value


def _out_frame() -> np.ndarray:
    return np.zeros((FRAME_SIZE, 1), dtype=np.float32)


def _make_primed_engine(*args, **kwargs) -> AudioEngine:
    """D-015: priming(起動直後にPRIME_TARGET_FRAMESフレーム溜まるまで出力しない)は
    ジッタバッファ自体の検証(TestJitterBuffer/TestPriming)以外のテストの関心事
    ではない。それらのテストでは「1フレームpushで即pop出力される」という
    priming導入前の前提を保ったまま検証したいため、priming済み状態から始める。
    """
    engine = AudioEngine(*args, **kwargs)
    engine._primed = True
    return engine


def _push_and_pop_once(engine: AudioEngine, value: float) -> np.ndarray:
    engine._input_callback(_in_frame(value), FRAME_SIZE, None, None)
    outdata = _out_frame()
    engine._output_callback(outdata, FRAME_SIZE, None, None)
    return outdata[:, 0]


# --- 入力側コールバック: 例外保護(bypass+on_error契約)の移植 -------------------


def test_input_callback_falls_back_to_bypass_and_reports_error_when_chain_raises():
    errors = []
    engine = _make_primed_engine(_FailingChain(), on_error=errors.append)
    indata = _in_frame(0.3)

    engine._input_callback(indata, FRAME_SIZE, None, None)
    outdata = _out_frame()
    engine._output_callback(outdata, FRAME_SIZE, None, None)

    np.testing.assert_allclose(outdata[:, 0], indata[:, 0])  # 未加工の入力へフォールバック
    assert errors == ["boom"]


def test_input_callback_recovers_on_next_frame_after_transient_error():
    """1フレームで例外が起きても、処理が完全に止まらず次のフレームから正常に戻る。"""
    calls = {"n": 0}

    class FlakyChain:
        def process(self, frame):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")
            return frame * 0.5, 1.0

    errors = []
    engine = _make_primed_engine(FlakyChain(), on_error=errors.append)
    indata = _in_frame(0.4)

    engine._input_callback(indata, FRAME_SIZE, None, None)
    outdata1 = _out_frame()
    engine._output_callback(outdata1, FRAME_SIZE, None, None)
    assert len(errors) == 1
    np.testing.assert_allclose(outdata1[:, 0], indata[:, 0])

    engine._input_callback(indata, FRAME_SIZE, None, None)
    outdata2 = _out_frame()
    engine._output_callback(outdata2, FRAME_SIZE, None, None)
    assert len(errors) == 1  # 2回目はエラーが増えない
    np.testing.assert_allclose(outdata2[:, 0], indata[:, 0] * 0.5)


def test_input_callback_without_on_error_does_not_raise():
    engine = _make_primed_engine(_FailingChain())  # on_error未指定
    indata = _in_frame(0.1)
    engine._input_callback(indata, FRAME_SIZE, None, None)  # 例外を送出しないこと
    outdata = _out_frame()
    engine._output_callback(outdata, FRAME_SIZE, None, None)
    np.testing.assert_allclose(outdata[:, 0], indata[:, 0])


def test_input_callback_normal_path_still_works():
    engine = _make_primed_engine(_PassthroughChain())
    indata = _in_frame(0.2)
    engine._input_callback(indata, FRAME_SIZE, None, None)
    outdata = _out_frame()
    engine._output_callback(outdata, FRAME_SIZE, None, None)
    np.testing.assert_allclose(outdata[:, 0], indata[:, 0] * 2.0)


def test_input_callback_bypass_mode_ignores_chain_entirely():
    engine = _make_primed_engine(_FailingChain())
    engine.bypass = True
    indata = _in_frame(0.55)
    engine._input_callback(indata, FRAME_SIZE, None, None)
    outdata = _out_frame()
    engine._output_callback(outdata, FRAME_SIZE, None, None)
    np.testing.assert_allclose(outdata[:, 0], indata[:, 0])


# --- ジッタバッファ: 順序保持・満杯時の破棄・空時の無音 -------------------------


class TestJitterBuffer:
    def test_frames_are_popped_in_the_order_they_were_pushed(self):
        engine = AudioEngine(_PassthroughChain())
        values = [0.1, 0.2, 0.3]
        for v in values:
            engine._input_callback(_in_frame(v), FRAME_SIZE, None, None)

        for v in values:
            outdata = _out_frame()
            engine._output_callback(outdata, FRAME_SIZE, None, None)
            np.testing.assert_allclose(outdata[:, 0], np.full(FRAME_SIZE, v * 2.0, dtype=np.float32))

    def test_buffer_full_drops_oldest_frame_without_raising(self):
        engine = AudioEngine(_PassthroughChain())
        # バッファ上限を超える数のフレームを積む(最古から破棄されるはず)。
        total = JITTER_BUFFER_FRAMES + 3
        for i in range(total):
            engine._input_callback(_in_frame(float(i)), FRAME_SIZE, None, None)
            assert len(engine._buffer) <= JITTER_BUFFER_FRAMES  # 例外を出さず上限内に収まる

        # 生き残っているのは直近JITTER_BUFFER_FRAMES件(値0.0〜2.0は破棄済み)のはず。
        expected_first_surviving = total - JITTER_BUFFER_FRAMES
        for i in range(expected_first_surviving, total):
            outdata = _out_frame()
            engine._output_callback(outdata, FRAME_SIZE, None, None)
            np.testing.assert_allclose(
                outdata[:, 0], np.full(FRAME_SIZE, float(i) * 2.0, dtype=np.float32)
            )

    def test_output_callback_returns_silence_when_buffer_is_empty(self):
        engine = AudioEngine(_PassthroughChain())
        outdata = _out_frame()
        outdata[:, 0] = 1.0  # 未初期化メモリを模して非ゼロで埋めておく

        engine._output_callback(outdata, FRAME_SIZE, None, None)  # 例外を送出しないこと

        np.testing.assert_allclose(outdata[:, 0], np.zeros(FRAME_SIZE, dtype=np.float32))


# --- priming: 起動直後・アンダーラン後はPRIME_TARGET_FRAMES溜まるまで出力しない (D-015) --


class TestPriming:
    def test_engine_starts_unprimed(self):
        engine = AudioEngine(_PassthroughChain())
        assert engine._primed is False

    def test_output_stays_silent_until_prime_target_is_reached(self):
        engine = AudioEngine(_PassthroughChain())
        assert PRIME_TARGET_FRAMES >= 2, "test assumes at least 2 frames are needed to prime"

        # PRIME_TARGET_FRAMES未満しか溜まっていない間は、出力は無音でポップもされない。
        for i in range(PRIME_TARGET_FRAMES - 1):
            engine._input_callback(_in_frame(float(i + 1)), FRAME_SIZE, None, None)
            outdata = _out_frame()
            engine._output_callback(outdata, FRAME_SIZE, None, None)
            np.testing.assert_allclose(outdata[:, 0], np.zeros(FRAME_SIZE, dtype=np.float32))
            assert engine._primed is False
            assert len(engine._buffer) == i + 1  # ポップされていない

    def test_output_resumes_once_prime_target_is_reached(self):
        engine = AudioEngine(_PassthroughChain())
        for i in range(PRIME_TARGET_FRAMES - 1):
            engine._input_callback(_in_frame(float(i + 1)), FRAME_SIZE, None, None)
            engine._output_callback(_out_frame(), FRAME_SIZE, None, None)

        # 目標フレーム数に達した後の最初の入力で、priming状態が解除され通常再生に戻る。
        engine._input_callback(_in_frame(9.0), FRAME_SIZE, None, None)
        outdata = _out_frame()
        engine._output_callback(outdata, FRAME_SIZE, None, None)
        assert engine._primed is True
        np.testing.assert_allclose(outdata[:, 0], np.full(FRAME_SIZE, 1.0 * 2.0, dtype=np.float32))

    def test_underrun_after_priming_returns_to_priming_state(self):
        """primed状態でバッファが空になった(アンダーラン)場合、再度priming状態へ戻り、
        PRIME_TARGET_FRAMES溜まるまでポップを再開しない(D-015)。"""
        engine = AudioEngine(_PassthroughChain())
        for i in range(PRIME_TARGET_FRAMES):
            engine._input_callback(_in_frame(float(i + 1)), FRAME_SIZE, None, None)
        # 溜めたフレームをすべてポップし切ってバッファを空にする(アンダーラン発生)。
        for _ in range(PRIME_TARGET_FRAMES):
            engine._output_callback(_out_frame(), FRAME_SIZE, None, None)
        assert engine._primed is True  # ポップし切るまではprimed状態が続く

        engine._output_callback(_out_frame(), FRAME_SIZE, None, None)  # ここでアンダーラン
        assert engine._primed is False

        # 1フレームだけpushしても(PRIME_TARGET_FRAMES未満)、すぐにはポップされない。
        engine._input_callback(_in_frame(42.0), FRAME_SIZE, None, None)
        outdata = _out_frame()
        engine._output_callback(outdata, FRAME_SIZE, None, None)
        if PRIME_TARGET_FRAMES > 1:
            np.testing.assert_allclose(outdata[:, 0], np.zeros(FRAME_SIZE, dtype=np.float32))
            assert engine._primed is False


# --- メーター: 出力側は実際に書き出す値(アンダーラン時の無音を含む)を測る -------


class TestMeterMeasuresActualOutput:
    def test_output_meter_reflects_underrun_silence_not_stale_input_level(self):
        meter_calls = []
        engine = _make_primed_engine(_PassthroughChain(), on_meter_update=lambda *args: meter_calls.append(args))

        engine._input_callback(_in_frame(0.9), FRAME_SIZE, None, None)
        engine._output_callback(_out_frame(), FRAME_SIZE, None, None)  # バッファを空にする
        in_rms_1, in_peak_1, out_rms_1, out_peak_1 = meter_calls[-1]
        assert out_rms_1 > engine._output_meter.floor_db  # 実際に音を書き出した

        # 新しい入力を送らずに再度出力コールバックを呼ぶ(アンダーラン)。
        engine._output_callback(_out_frame(), FRAME_SIZE, None, None)
        in_rms_2, in_peak_2, out_rms_2, out_peak_2 = meter_calls[-1]

        assert in_rms_2 == in_rms_1  # 入力メーターは直近の入力コールバック時の値のまま
        assert in_peak_2 == in_peak_1
        # 出力メーターは無音(floor_db)を反映し、直前の入力レベルへ引きずられない。
        assert out_rms_2 == pytest.approx(engine._output_meter.floor_db)


# --- start()/stop(): 2ストリームへ拡張したリーク防止・確実な後始末 --------------


class _FakeStream:
    """sd.InputStream(...)/sd.OutputStream(...)相当のフェイク。Pa_OpenStreamは
    成功、Pa_StartStream/Pa_StopStream/close()それぞれ独立に失敗/成功を
    制御できるようにする(Reviewer指摘Medium対応の回帰テスト用)。"""

    def __init__(
        self,
        start_should_fail: bool = False,
        stop_should_fail: bool = False,
        close_should_fail: bool = False,
        **_kwargs,
    ):
        self.start_should_fail = start_should_fail
        self.stop_should_fail = stop_should_fail
        self.close_should_fail = close_should_fail
        self.start_called = False
        self.close_called = False
        self.stop_called = False

    def start(self):
        self.start_called = True
        if self.start_should_fail:
            raise RuntimeError("Pa_StartStream failed (device busy)")

    def close(self):
        self.close_called = True
        if self.close_should_fail:
            raise RuntimeError("close() failed")

    def stop(self):
        self.stop_called = True
        if self.stop_should_fail:
            raise RuntimeError("Pa_StopStream failed (device disconnected)")


class TestStartOpensBothStreamsAndCleansUpOnFailure:
    """D-009: 入力(SoloCast)/出力(CABLE Input)を独立したストリームとして開く。
    D-006で確立した単一ストリームのリーク防止パターンを2ストリームへ拡張する。
    """

    def test_both_streams_start_successfully(self, monkeypatch):
        input_stream = _FakeStream()
        output_stream = _FakeStream()
        monkeypatch.setattr(engine_mod.sd, "InputStream", lambda **kwargs: input_stream)
        monkeypatch.setattr(engine_mod.sd, "OutputStream", lambda **kwargs: output_stream)

        engine = AudioEngine(_PassthroughChain())
        engine.start()

        assert input_stream.start_called is True
        assert output_stream.start_called is True
        assert input_stream.close_called is False
        assert output_stream.close_called is False
        assert engine.is_running() is True

    def test_input_stream_start_failure_never_creates_output_stream(self, monkeypatch):
        input_stream = _FakeStream(start_should_fail=True)
        output_created = {"called": False}

        def _make_output(**kwargs):
            output_created["called"] = True
            return _FakeStream()

        monkeypatch.setattr(engine_mod.sd, "InputStream", lambda **kwargs: input_stream)
        monkeypatch.setattr(engine_mod.sd, "OutputStream", _make_output)

        engine = AudioEngine(_PassthroughChain())
        with pytest.raises(RuntimeError, match="Pa_StartStream failed"):
            engine.start()

        assert input_stream.close_called is True  # 開いた入力側はcloseされる
        assert output_created["called"] is False  # 出力側は開始すらされない
        assert engine._input_stream is None
        assert engine._output_stream is None
        assert engine.is_running() is False

    def test_output_stream_start_failure_closes_already_started_input_stream(self, monkeypatch):
        input_stream = _FakeStream(start_should_fail=False)
        output_stream = _FakeStream(start_should_fail=True)
        monkeypatch.setattr(engine_mod.sd, "InputStream", lambda **kwargs: input_stream)
        monkeypatch.setattr(engine_mod.sd, "OutputStream", lambda **kwargs: output_stream)

        engine = AudioEngine(_PassthroughChain())
        with pytest.raises(RuntimeError, match="Pa_StartStream failed"):
            engine.start()

        assert input_stream.start_called is True
        assert input_stream.stop_called is True  # 開始済みの入力側はstop
        assert input_stream.close_called is True  # ...してからclose
        assert output_stream.close_called is True  # 出力側自身もPa_StartStream失敗でclose
        assert engine._input_stream is None
        assert engine._output_stream is None
        assert engine.is_running() is False

    def test_repeated_start_stop_failures_never_leave_a_dangling_stream(self, monkeypatch):
        """高頻度start/stop(デバイス切り替え・処理ON/OFF連打)で出力側のPa_StartStream
        のみが繰り返し失敗しても、失敗するたびに毎回closeされ、参照が蓄積しないこと。"""
        created_inputs = []
        created_outputs = []

        def _make_input(**kwargs):
            stream = _FakeStream(start_should_fail=False)
            created_inputs.append(stream)
            return stream

        def _make_output(**kwargs):
            stream = _FakeStream(start_should_fail=True)
            created_outputs.append(stream)
            return stream

        monkeypatch.setattr(engine_mod.sd, "InputStream", _make_input)
        monkeypatch.setattr(engine_mod.sd, "OutputStream", _make_output)

        engine = AudioEngine(_PassthroughChain())
        for _ in range(50):
            with pytest.raises(RuntimeError):
                engine.start()

        assert len(created_inputs) == 50
        assert len(created_outputs) == 50
        assert all(s.close_called for s in created_inputs)
        assert all(s.close_called for s in created_outputs)
        assert engine._input_stream is None
        assert engine._output_stream is None

    def test_input_cleanup_stop_failure_does_not_mask_original_output_failure(self, monkeypatch):
        """Reviewer再指摘(Medium, CONFIRMED)への対応。

        出力側のPa_StartStream失敗をトリガに入力側を後始末する際、
        入力側自身の.stop()が例外を送出しても、(a)入力側の.close()は
        スキップされずに呼ばれ、(b)最終的に伝播する例外は入力側のstop()失敗
        ではなく、ユーザーに伝えるべき本来の原因(出力側のPa_StartStream失敗)
        のままであること。
        """
        input_stream = _FakeStream(start_should_fail=False, stop_should_fail=True)
        output_stream = _FakeStream(start_should_fail=True)
        monkeypatch.setattr(engine_mod.sd, "InputStream", lambda **kwargs: input_stream)
        monkeypatch.setattr(engine_mod.sd, "OutputStream", lambda **kwargs: output_stream)

        engine = AudioEngine(_PassthroughChain())
        with pytest.raises(RuntimeError, match="Pa_StartStream failed") as exc_info:
            engine.start()

        # 伝播した例外は出力側の元の失敗理由であり、入力側のstop()失敗ではない。
        assert "Pa_StopStream" not in str(exc_info.value)
        assert input_stream.stop_called is True
        assert input_stream.close_called is True  # stop()失敗でclose()がスキップされない
        assert output_stream.close_called is True
        assert engine._input_stream is None
        assert engine._output_stream is None
        assert engine.is_running() is False


class TestStop:
    def test_stop_stops_and_closes_both_streams(self, monkeypatch):
        input_stream = _FakeStream()
        output_stream = _FakeStream()
        monkeypatch.setattr(engine_mod.sd, "InputStream", lambda **kwargs: input_stream)
        monkeypatch.setattr(engine_mod.sd, "OutputStream", lambda **kwargs: output_stream)

        engine = AudioEngine(_PassthroughChain())
        engine.start()
        engine.stop()

        assert input_stream.stop_called is True
        assert input_stream.close_called is True
        assert output_stream.stop_called is True
        assert output_stream.close_called is True
        assert engine._input_stream is None
        assert engine._output_stream is None
        assert engine.is_running() is False

    def test_stop_without_start_does_not_raise(self):
        engine = AudioEngine(_PassthroughChain())
        engine.stop()  # 例外を送出しないこと
        assert engine.is_running() is False

    def test_input_stream_stop_failure_does_not_skip_output_stream_cleanup(self, monkeypatch):
        """Reviewer再指摘(Medium, CONFIRMED)への対応。

        入力ストリームの.stop()が例外を送出しても、(a)入力ストリーム自身の
        .close()はスキップされず、(b)出力ストリームのstop()/close()も
        実行され、(c)両方の参照がNoneにクリアされ、(d)stop()自体は
        呼び出し元(app.pyの_stop_engine()等)へ例外を伝播させない
        (片方の失敗が全体のクリーンアップを止めない)。
        """
        input_stream = _FakeStream(stop_should_fail=True)
        output_stream = _FakeStream()
        monkeypatch.setattr(engine_mod.sd, "InputStream", lambda **kwargs: input_stream)
        monkeypatch.setattr(engine_mod.sd, "OutputStream", lambda **kwargs: output_stream)

        engine = AudioEngine(_PassthroughChain())
        engine.start()
        engine.stop()  # 例外を送出しないこと

        assert input_stream.stop_called is True
        assert input_stream.close_called is True  # stop()失敗でclose()がスキップされない
        assert output_stream.stop_called is True  # 入力側の失敗が出力側の後始末を妨げない
        assert output_stream.close_called is True
        assert engine._input_stream is None
        assert engine._output_stream is None
        assert engine.is_running() is False

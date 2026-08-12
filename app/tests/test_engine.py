"""AudioEngineのコールバック内エラー処理・ストリーム開始失敗時の後始末を検証する。

実際のsounddeviceストリーム(実オーディオデバイス)はこの環境では扱えないため、
`AudioEngine._callback`をPortAudioを介さず直接呼び出して検証する。ストリーム開始の
検証は`sd.Stream`をフェイクに差し替えて行う。
"""

from __future__ import annotations

import numpy as np
import pytest

from soloclarity.audio import engine as engine_mod
from soloclarity.audio.engine import AudioEngine
from soloclarity.dsp.chain import FRAME_SIZE


class _FailingChain:
    def process(self, frame):
        raise ValueError("boom")


class _PassthroughChain:
    def process(self, frame):
        return frame * 2.0, 1.0


def _frame(value: float) -> np.ndarray:
    return np.ones((FRAME_SIZE, 1), dtype=np.float32) * value


def test_callback_falls_back_to_bypass_and_reports_error_when_chain_raises():
    errors = []
    engine = AudioEngine(_FailingChain(), on_error=errors.append)
    indata = _frame(0.3)
    outdata = np.zeros((FRAME_SIZE, 1), dtype=np.float32)

    engine._callback(indata, outdata, FRAME_SIZE, None, None)

    np.testing.assert_allclose(outdata[:, 0], indata[:, 0])  # 未加工の入力へフォールバック
    assert errors == ["boom"]


def test_callback_recovers_on_next_frame_after_transient_error():
    """1フレームで例外が起きても、処理が完全に止まらず次のフレームから正常に戻る。"""
    calls = {"n": 0}

    class FlakyChain:
        def process(self, frame):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")
            return frame * 0.5, 1.0

    errors = []
    engine = AudioEngine(FlakyChain(), on_error=errors.append)
    indata = _frame(0.4)

    outdata1 = np.zeros((FRAME_SIZE, 1), dtype=np.float32)
    engine._callback(indata, outdata1, FRAME_SIZE, None, None)
    assert len(errors) == 1
    np.testing.assert_allclose(outdata1[:, 0], indata[:, 0])

    outdata2 = np.zeros((FRAME_SIZE, 1), dtype=np.float32)
    engine._callback(indata, outdata2, FRAME_SIZE, None, None)
    assert len(errors) == 1  # 2回目はエラーが増えない
    np.testing.assert_allclose(outdata2[:, 0], indata[:, 0] * 0.5)


def test_callback_without_on_error_does_not_raise():
    engine = AudioEngine(_FailingChain())  # on_error未指定
    indata = _frame(0.1)
    outdata = np.zeros((FRAME_SIZE, 1), dtype=np.float32)
    engine._callback(indata, outdata, FRAME_SIZE, None, None)  # 例外を送出しないこと
    np.testing.assert_allclose(outdata[:, 0], indata[:, 0])


def test_callback_normal_path_still_works():
    engine = AudioEngine(_PassthroughChain())
    indata = _frame(0.2)
    outdata = np.zeros((FRAME_SIZE, 1), dtype=np.float32)
    engine._callback(indata, outdata, FRAME_SIZE, None, None)
    np.testing.assert_allclose(outdata[:, 0], indata[:, 0] * 2.0)


def test_callback_bypass_mode_ignores_chain_entirely():
    engine = AudioEngine(_FailingChain())
    engine.bypass = True
    indata = _frame(0.55)
    outdata = np.zeros((FRAME_SIZE, 1), dtype=np.float32)
    engine._callback(indata, outdata, FRAME_SIZE, None, None)
    np.testing.assert_allclose(outdata[:, 0], indata[:, 0])


class _FakeStream:
    """sd.Stream(...)相当のフェイク。Pa_OpenStreamは成功、Pa_StartStreamのみ
    失敗/成功を制御できるようにする。"""

    def __init__(self, start_should_fail: bool = False, **_kwargs):
        self.start_should_fail = start_should_fail
        self.start_called = False
        self.close_called = False
        self.stop_called = False

    def start(self):
        self.start_called = True
        if self.start_should_fail:
            raise RuntimeError("Pa_StartStream failed (device busy)")

    def close(self):
        self.close_called = True

    def stop(self):
        self.stop_called = True


class TestStartClosesStreamOnPaStartStreamFailure:
    """Reviewer指摘2(High, CONFIRMED)への対応。

    sd.Stream(...)(Pa_OpenStream相当)は成功したが.start()(Pa_StartStream相当)が
    失敗した場合、開いたストリームをcloseしないとネイティブハンドルがリークする
    (sounddevice.Streamに__del__は無い)。
    """

    def test_stream_is_closed_when_start_fails(self, monkeypatch):
        fake_stream = _FakeStream(start_should_fail=True)
        monkeypatch.setattr(engine_mod.sd, "Stream", lambda **kwargs: fake_stream)

        engine = AudioEngine(_PassthroughChain())
        with pytest.raises(RuntimeError, match="Pa_StartStream failed"):
            engine.start()

        assert fake_stream.start_called is True
        assert fake_stream.close_called is True  # リークせずcloseされること
        assert engine._stream is None  # 失敗した参照を保持しない
        assert engine.is_running() is False

    def test_stream_is_not_closed_on_successful_start(self, monkeypatch):
        fake_stream = _FakeStream(start_should_fail=False)
        monkeypatch.setattr(engine_mod.sd, "Stream", lambda **kwargs: fake_stream)

        engine = AudioEngine(_PassthroughChain())
        engine.start()

        assert fake_stream.close_called is False
        assert engine._stream is fake_stream
        assert engine.is_running() is True

    def test_repeated_start_stop_failures_never_leave_a_dangling_stream(self, monkeypatch):
        """高頻度start/stop(デバイス切り替え・処理ON/OFF連打)でPa_StartStreamのみが
        繰り返し失敗しても、失敗するたびに毎回closeされ、参照が蓄積しないこと。"""
        created_streams = []

        def _make_stream(**kwargs):
            stream = _FakeStream(start_should_fail=True)
            created_streams.append(stream)
            return stream

        monkeypatch.setattr(engine_mod.sd, "Stream", _make_stream)

        engine = AudioEngine(_PassthroughChain())
        for _ in range(50):
            with pytest.raises(RuntimeError):
                engine.start()

        assert len(created_streams) == 50
        assert all(s.close_called for s in created_streams)
        assert engine._stream is None

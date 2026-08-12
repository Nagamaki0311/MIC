"""AudioEngineのコールバック内エラー処理を検証する。

実際のsounddeviceストリーム(実オーディオデバイス)はこの環境では扱えないため、
`AudioEngine._callback`をPortAudioを介さず直接呼び出して検証する。
"""

from __future__ import annotations

import numpy as np

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

"""RNNoiseの発話確率に基づくノイズゲート。

レベル閾値ではなく発話確率(0.0-1.0)を主信号にすることで、
小さい声をレベルの小ささだけを理由に誤って遮断しないようにする(D-001)。
"""

from __future__ import annotations

import math

import numpy as np

FRAME_SIZE = 480
SAMPLE_RATE = 48000
FRAME_DURATION_MS = 1000.0 * FRAME_SIZE / SAMPLE_RATE  # 10.0ms


def _time_constant_coeff(time_ms: float, frame_duration_ms: float = FRAME_DURATION_MS) -> float:
    """フレーム単位の一次(exponential)減衰係数を、時定数(ms)から求める。"""
    if time_ms <= 0.0:
        return 0.0
    return math.exp(-frame_duration_ms / time_ms)


class SpeechProbabilityGate:
    """発話確率が閾値未満の間はゲインを絞る。閉じる速さはrelease_msで指定する。"""

    def __init__(self, threshold: float, release_ms: float, attack_ms: float = 5.0):
        self.threshold = threshold
        self.release_ms = release_ms
        self.attack_ms = attack_ms
        self._attack_coeff = _time_constant_coeff(attack_ms)
        self._release_coeff = _time_constant_coeff(release_ms)
        self._gain = 0.0

    def apply(self, frame: np.ndarray, speech_prob: float) -> np.ndarray:
        target = 1.0 if speech_prob >= self.threshold else 0.0
        coeff = self._attack_coeff if target > self._gain else self._release_coeff
        self._gain = target + (self._gain - target) * coeff
        return frame * self._gain

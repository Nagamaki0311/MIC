"""自前AGC(オートレベラー)実装。

RMSエンベロープに基づく低速なゲイン補正。既存ライブラリに該当機能がないため自前実装する
(D-001)。発話確率が閾値未満の間(無音・非発話区間)はゲイン更新を凍結し、
無音時のノイズに反応してゲインが暴れることを防ぐ。
"""

from __future__ import annotations

import math

import numpy as np

from soloclarity.dsp.meter import rms

FRAME_SIZE = 480
SAMPLE_RATE = 48000
FRAME_DURATION_S = FRAME_SIZE / SAMPLE_RATE  # 0.01s


def _time_constant_coeff(time_seconds: float, frame_duration_s: float = FRAME_DURATION_S) -> float:
    if time_seconds <= 0.0:
        return 0.0
    return math.exp(-frame_duration_s / time_seconds)


class AutomaticGainControl:
    """RMSエンベロープをtarget_dbfsへ寄せるようゲインをゆっくり調整する。"""

    def __init__(
        self,
        target_dbfs: float,
        max_gain_db: float,
        attack_seconds: float = 1.0,
        release_seconds: float = 3.0,
        freeze_speech_prob_threshold: float = 0.3,
    ):
        self.target_linear = 10.0 ** (target_dbfs / 20.0)
        self.max_gain_linear = 10.0 ** (max_gain_db / 20.0)
        self.min_gain_linear = 1.0 / self.max_gain_linear
        self.freeze_speech_prob_threshold = freeze_speech_prob_threshold
        self._attack_coeff = _time_constant_coeff(attack_seconds)
        self._release_coeff = _time_constant_coeff(release_seconds)
        # エンベロープはtarget付近から始め、起動直後に極端なゲインへ飛ばないようにする。
        self._rms_envelope = self.target_linear
        self._gain = 1.0

    def process(self, frame: np.ndarray, speech_prob: float) -> np.ndarray:
        frame_rms = rms(frame)
        if speech_prob >= self.freeze_speech_prob_threshold and frame_rms > 1e-6:
            coeff = self._attack_coeff if frame_rms > self._rms_envelope else self._release_coeff
            self._rms_envelope = frame_rms + (self._rms_envelope - frame_rms) * coeff
            desired_gain = self.target_linear / max(self._rms_envelope, 1e-9)
            self._gain = min(max(desired_gain, self.min_gain_linear), self.max_gain_linear)
        # 発話確率が低い間は self._gain を更新せず直前の値を保持する(凍結)。
        return frame * self._gain

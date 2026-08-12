"""RMS/ピークレベルの計算とGUI表示用のdBFSメーター。"""

from __future__ import annotations

import numpy as np


def rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))


def peak(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    return float(np.max(np.abs(frame)))


def linear_to_dbfs(value: float, floor_db: float = -100.0) -> float:
    if value <= 0.0:
        return floor_db
    return max(20.0 * float(np.log10(value)), floor_db)


class LevelMeter:
    """フレームごとにRMS/ピークを更新し、GUI表示用のdBFS値を保持する。

    ピークは瞬時値ではなく、ゆっくり減衰するピークホールドとして表示側で見やすくする。
    """

    def __init__(self, floor_db: float = -60.0, peak_decay_per_frame: float = 0.95):
        self.floor_db = floor_db
        self._peak_decay = peak_decay_per_frame
        self._peak_linear = 0.0
        self.rms_dbfs = floor_db
        self.peak_dbfs = floor_db

    def update(self, frame: np.ndarray) -> tuple[float, float]:
        frame_rms = rms(frame)
        frame_peak = peak(frame)
        self._peak_linear = max(frame_peak, self._peak_linear * self._peak_decay)
        self.rms_dbfs = linear_to_dbfs(frame_rms, self.floor_db)
        self.peak_dbfs = linear_to_dbfs(self._peak_linear, self.floor_db)
        return self.rms_dbfs, self.peak_dbfs

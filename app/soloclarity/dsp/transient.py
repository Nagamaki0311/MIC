"""キー打鍵等の瞬間的なインパクト音を検出する軽量トランジェント検出器。

WebRTC Audio Processingの`TransientSuppressor`相当の機能を持つ既存ライブラリが
見つからなかったため自前実装する(D-012)。フレーム(480サンプル=10ms)ごとのRMSに
対し、速いエンベロープと遅いエンベロープの比からそのフレームがどれだけ
「インパクト音らしいか」を0.0-1.0の連続値で返す。ハードな2値判定にしないことで、
声の自然な強弱(緩やかな立ち上がり)を打鍵音と誤認しにくくする。
"""

from __future__ import annotations

import numpy as np

from soloclarity.dsp.meter import linear_to_dbfs, rms

FAST_ENV_COEFF = 0.7  # 速いエンベロープのEMA係数(約14ms相当)
SLOW_ENV_COEFF = 0.05  # 遅いエンベロープのEMA係数(約200ms相当)
TRANSIENT_RATIO_THRESHOLD = 2.2  # このratio以上でtransient_score=1.0に飽和する
SILENCE_FLOOR_DBFS = -45.0  # このRMSレベル未満は無音相当としてtransient_scoreを0固定


class TransientDetector:
    """フレームごとのRMSから、インパクト音らしさ(0.0-1.0)を連続値で返す。"""

    def __init__(self) -> None:
        self._fast_env = 0.0
        self._slow_env = 0.0

    def process(self, frame: np.ndarray) -> float:
        frame_rms = rms(frame)
        self._fast_env += (frame_rms - self._fast_env) * FAST_ENV_COEFF
        self._slow_env += (frame_rms - self._slow_env) * SLOW_ENV_COEFF

        if linear_to_dbfs(frame_rms) < SILENCE_FLOOR_DBFS:
            return 0.0

        ratio = self._fast_env / (self._slow_env + 1e-6)
        score = (ratio - 1.0) / (TRANSIENT_RATIO_THRESHOLD - 1.0)
        return min(max(score, 0.0), 1.0)

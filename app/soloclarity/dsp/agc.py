"""自前AGC(オートレベラー)実装。

RMSエンベロープに基づくゲイン補正。既存ライブラリに該当機能がないため自前実装する
(D-001)。発話が非アクティブな間(無音・非発話区間)はゲイン更新を凍結し、
無音時のノイズに反応してゲインが暴れることを防ぐ。

D-015: 発話状態の判定はAGC独自のfreeze_speech_prob_threshold(0.3固定)ではなく、
gate.SpeechActivityTracker(ヒステリシス+hangover付き)へ一元化し、VoiceChain経由で
speech_active(bool)として受け取る。またCompressorにmakeup gain機構が無いため、
AGCの収束が既定attack/release(旧2.0秒/4.0秒)では発話区間内に収束しきらず「十分な
声量でも遠く/小さく聞こえる」原因になっていた。時定数を短縮し(既定0.4秒/1.5秒)、
ゲイン適用もフレーム内で線形ランプさせて波形の不連続を避ける。
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
    """RMSエンベロープをtarget_dbfsへ寄せるようゲインを調整する。"""

    def __init__(
        self,
        target_dbfs: float,
        max_gain_db: float,
        attack_seconds: float = 1.0,
        release_seconds: float = 3.0,
    ):
        self.set_params(
            target_dbfs=target_dbfs,
            max_gain_db=max_gain_db,
            attack_seconds=attack_seconds,
            release_seconds=release_seconds,
        )
        # エンベロープはtarget付近から始め、起動直後に極端なゲインへ飛ばないようにする。
        self._rms_envelope = self.target_linear
        self._gain = 1.0

    def set_params(
        self,
        target_dbfs: float,
        max_gain_db: float,
        attack_seconds: float = 1.0,
        release_seconds: float = 3.0,
    ) -> None:
        """既存インスタンスの係数だけを更新する(D-015: ゲイン・エンベロープ等の
        内部状態はリセットしない。詳細設定スライダー操作のたびに声が一瞬消える
        バグの修正)。"""
        self.target_dbfs = target_dbfs
        self.max_gain_db = max_gain_db
        self.attack_seconds = attack_seconds
        self.release_seconds = release_seconds
        self.target_linear = 10.0 ** (target_dbfs / 20.0)
        self.max_gain_linear = 10.0 ** (max_gain_db / 20.0)
        self.min_gain_linear = 1.0 / self.max_gain_linear
        self._attack_coeff = _time_constant_coeff(attack_seconds)
        self._release_coeff = _time_constant_coeff(release_seconds)

    def process(self, frame: np.ndarray, speech_active: bool) -> np.ndarray:
        frame_rms = rms(frame)
        if speech_active and frame_rms > 1e-6:
            coeff = self._attack_coeff if frame_rms > self._rms_envelope else self._release_coeff
            self._rms_envelope = frame_rms + (self._rms_envelope - frame_rms) * coeff
            desired_gain = self.target_linear / max(self._rms_envelope, 1e-9)
            new_gain = min(max(desired_gain, self.min_gain_linear), self.max_gain_linear)
        else:
            # 発話が非アクティブな間は self._gain を更新せず直前の値を保持する(凍結)。
            new_gain = self._gain
        ramp = np.linspace(self._gain, new_gain, len(frame), dtype=np.float32)
        self._gain = new_gain
        return frame * ramp

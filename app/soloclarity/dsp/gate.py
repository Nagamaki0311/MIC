"""RNNoiseの発話確率に基づくノイズゲートと、発話状態(アクティブ/非アクティブ)の一元管理。

レベル閾値ではなく発話確率(0.0-1.0)を主信号にすることで、
小さい声をレベルの小ささだけを理由に誤って遮断しないようにする(D-001)。

D-015: 発話確率の生値を毎フレーム閾値と比較する2値判定(ヒステリシスなし)+
完全ミュート+フレーム単位ステップのゲイン適用は、低い声・小さい声で発話確率が
閾値付近を振動した際に頻繁な開閉・完全な音の消失・フレーム境界のクリックを
同時に起こし「プツプツ途切れる」の最有力機構だった。このため
(1) ヒステリシス(開く閾値と閉じる閾値=開く閾値×0.5を分ける)とhangover(200ms、
閾値を割ってもすぐには閉じない)を持つSpeechActivityTrackerへ発話状態判定を一元化し、
AGC(agc.py)とゲートの両方がこれを共有する、
(2) ゲートの閉時ターゲットを完全無音(0.0)ではなくGATE_FLOOR_DBへのダッキングとし、
(3) ゲインをフレーム単位のステップではなくフレーム内で前回値から今回値へ線形ランプさせる。
"""

from __future__ import annotations

import math

import numpy as np

FRAME_SIZE = 480
SAMPLE_RATE = 48000
FRAME_DURATION_MS = 1000.0 * FRAME_SIZE / SAMPLE_RATE  # 10.0ms

# 発話が閾値を割ってもすぐには非アクティブ扱いにしない猶予時間(D-015)。
SPEECH_ACTIVITY_HANGOVER_MS = 200.0
# ヒステリシスの閉じる閾値は、開く閾値(gate_threshold)に対する比率で決める。
SPEECH_ACTIVITY_CLOSE_THRESHOLD_RATIO = 0.5

# ゲート閉時のダッキング先(完全無音ではなくフロアへ)。無音時にわずかな残留ノイズを
# 許容する代わりに、開閉の閾値付近での完全な音の消失・クリックを避ける(D-015)。
GATE_FLOOR_DB = -18.0


def _time_constant_coeff(time_ms: float, frame_duration_ms: float = FRAME_DURATION_MS) -> float:
    """フレーム単位の一次(exponential)減衰係数を、時定数(ms)から求める。"""
    if time_ms <= 0.0:
        return 0.0
    return math.exp(-frame_duration_ms / time_ms)


class SpeechActivityTracker:
    """発話確率(0.0-1.0)から発話中/非発話中の2値状態を、ヒステリシス+hangoverで
    安定して求める。AGC・ゲートの両方がこの一元化された状態を参照する(D-015)。
    """

    def __init__(self, open_threshold: float, hangover_ms: float = SPEECH_ACTIVITY_HANGOVER_MS):
        self.set_params(open_threshold=open_threshold, hangover_ms=hangover_ms)
        self._active = False
        self._hangover_frames_remaining = 0

    def set_params(self, open_threshold: float, hangover_ms: float = SPEECH_ACTIVITY_HANGOVER_MS) -> None:
        self.open_threshold = open_threshold
        self.close_threshold = open_threshold * SPEECH_ACTIVITY_CLOSE_THRESHOLD_RATIO
        self.hangover_ms = hangover_ms
        self.hangover_frames = max(0, round(hangover_ms / FRAME_DURATION_MS))

    def update(self, speech_prob: float) -> bool:
        if speech_prob >= self.open_threshold:
            self._active = True
            self._hangover_frames_remaining = self.hangover_frames
        elif speech_prob < self.close_threshold:
            if self._hangover_frames_remaining > 0:
                self._hangover_frames_remaining -= 1
            else:
                self._active = False
        # close_threshold <= speech_prob < open_threshold の間は現在の状態を維持する
        # (ヒステリシス帯: ここで頻繁に開閉判定を切り替えない)。
        return self._active


class SpeechProbabilityGate:
    """発話が非アクティブな間はゲインをGATE_FLOOR_DBへダッキングする。

    完全ミュートではなくフロアへ寄せることで、発話状態判定が閾値付近を揺れても
    音が完全に消える瞬間を作らない。ゲインはフレーム内で前回値から今回値へ
    線形ランプさせ、フレーム境界での波形不連続(クリック)を避ける。
    """

    def __init__(self, threshold: float, release_ms: float, attack_ms: float = 5.0):
        self.set_params(threshold=threshold, release_ms=release_ms, attack_ms=attack_ms)
        # 起動直後は発話なしとみなし、フロア(閉状態の定常値)から始める。
        self._gain = self._floor_linear

    def set_params(self, threshold: float, release_ms: float, attack_ms: float = 5.0) -> None:
        self.threshold = threshold
        self.release_ms = release_ms
        self.attack_ms = attack_ms
        self._attack_coeff = _time_constant_coeff(attack_ms)
        self._release_coeff = _time_constant_coeff(release_ms)
        self._floor_linear = 10.0 ** (GATE_FLOOR_DB / 20.0)

    def apply(self, frame: np.ndarray, speech_active: bool) -> np.ndarray:
        target = 1.0 if speech_active else self._floor_linear
        coeff = self._attack_coeff if target > self._gain else self._release_coeff
        new_gain = target + (self._gain - target) * coeff
        ramp = np.linspace(self._gain, new_gain, len(frame), dtype=np.float32)
        self._gain = new_gain
        return frame * ramp

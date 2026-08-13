"""TransientDetector(app/soloclarity/dsp/transient.py)の単体テスト。

打鍵音のような単発インパクト音を検出しつつ、定常ノイズや声の自然な強弱を
誤ってインパクト音と判定しないことを合成信号で検証する。docs/decisions.md
D-012で確定した設計(fast_env/slow_envの比、無音フロア)をそのまま実装した
ことの直接検証であり、「実際に聞いて確認した」ものではない。

slow_env(EMA係数0.05, 時定数約200ms=20フレーム)はゼロ初期値から実際の
信号レベルへ収束するのに数十フレーム(実測でおよそ100フレーム=1秒)を要する
ため、各テストは十分なウォームアップの後の区間で判定する。
"""

from __future__ import annotations

import numpy as np

from soloclarity.dsp.chain import FRAME_SIZE, SAMPLE_RATE
from soloclarity.dsp.transient import TransientDetector

SETTLE_THRESHOLD = 0.15  # ウォームアップ後、定常信号が収束したとみなす閾値


def _make_frame(rng: np.random.Generator, amplitude: float) -> np.ndarray:
    return rng.normal(0.0, amplitude, FRAME_SIZE).astype(np.float32)


class TestStationaryNoiseConvergesLow:
    def test_transient_score_settles_low_for_steady_white_noise(self):
        detector = TransientDetector()
        rng = np.random.default_rng(1)

        scores = [detector.process(_make_frame(rng, 0.05)) for _ in range(150)]

        # slow_envが収束するまでのウォームアップ区間を除いた後半で低い値に収束すること。
        settled = scores[100:]
        assert all(
            s < SETTLE_THRESHOLD for s in settled
        ), f"steady noise should settle low, got {settled}"


class TestSinglePulseIsDetectedAndDecays:
    def test_pulse_after_steady_low_signal_spikes_then_recovers(self):
        detector = TransientDetector()
        rng = np.random.default_rng(2)

        # 定常な低振幅信号を十分流してエンベロープを馴染ませる。
        for _ in range(150):
            detector.process(_make_frame(rng, 0.02))

        # 打鍵音を模した単発の高振幅パルス(1フレームだけ振幅が大きい)。
        pulse_frame = rng.normal(0.0, 0.6, FRAME_SIZE).astype(np.float32)
        pulse_score = detector.process(pulse_frame)
        assert pulse_score >= 0.5, f"a sudden loud pulse should score high, got {pulse_score}"

        # パルス後、数フレームで元の低い値に戻る。
        recovery_scores = [detector.process(_make_frame(rng, 0.02)) for _ in range(10)]
        assert (
            recovery_scores[-1] < SETTLE_THRESHOLD
        ), f"score should decay back down, got {recovery_scores}"


class TestSilenceStaysZero:
    def test_transient_score_is_always_zero_during_silence(self):
        detector = TransientDetector()
        rng = np.random.default_rng(3)

        for _ in range(50):
            frame = rng.normal(0.0, 1e-5, FRAME_SIZE).astype(np.float32)
            assert detector.process(frame) == 0.0


class TestVoiceLikeSignalIsNotMisdetectedAsTransient:
    def test_gradual_voice_onset_scores_as_low_as_steady_noise(self):
        """基音+倍音の合成信号(声のモデル)を緩やかな立ち上がりで流した場合、
        定常ノイズと同程度にtransient_scoreが低いこと(声の自然な強弱を
        打鍵音と誤認しない)を確認する。"""
        detector = TransientDetector()
        sr = SAMPLE_RATE
        n_frames = 200
        t = np.arange(n_frames * FRAME_SIZE) / sr
        f0 = 130.0
        voice = np.zeros_like(t)
        for h in range(1, 10):
            voice += (1.0 / h) * np.sin(2 * np.pi * f0 * h * t)
        voice = voice / np.max(np.abs(voice))

        # 緩やかな立ち上がり(最初の20フレームで0→1へ線形に増幅)。
        ramp = np.clip(np.arange(len(voice)) / (20 * FRAME_SIZE), 0.0, 1.0)
        voice = (voice * ramp * 0.2).astype(np.float32)

        scores = [
            detector.process(voice[i : i + FRAME_SIZE]) for i in range(0, len(voice), FRAME_SIZE)
        ]
        settled = scores[100:]  # 立ち上がり完了+ウォームアップ後の区間
        assert all(
            s < SETTLE_THRESHOLD for s in settled
        ), f"gradual voice onset should not spike, got {settled}"

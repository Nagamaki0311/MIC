"""1フレーム(480サンプル, 48kHz, float32 mono, -1.0..1.0)を処理するDSPチェーン。

信号処理チェーン(仕様書 D-001 / docs/tasks.md T-001準拠):
入力 -> HighpassFilter -> RNNoise denoise(発話確率取得、wet/dry blend)
     -> EQ(PeakFilter束、明瞭度で強度可変) -> Compressor -> 自前AGC -> Limiter
     -> 発話確率ゲート -> 出力
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pedalboard

from soloclarity import presets
from soloclarity.dsp import rnnoise as rnnoise_mod
from soloclarity.dsp.agc import AutomaticGainControl
from soloclarity.dsp.gate import SpeechProbabilityGate

FRAME_SIZE = rnnoise_mod.FRAME_SIZE
SAMPLE_RATE = rnnoise_mod.SAMPLE_RATE


def _build_highpass_board(cutoff_hz: float) -> pedalboard.Pedalboard:
    return pedalboard.Pedalboard([pedalboard.HighpassFilter(cutoff_hz)])


def _build_eq_board(bands: tuple[presets.EqBand, ...]) -> pedalboard.Pedalboard:
    return pedalboard.Pedalboard(
        [pedalboard.PeakFilter(band.frequency_hz, band.gain_db, band.q) for band in bands]
    )


def _build_compressor_board(compressor: presets.CompressorParams) -> pedalboard.Pedalboard:
    return pedalboard.Pedalboard(
        [
            pedalboard.Compressor(
                threshold_db=compressor.threshold_db,
                ratio=compressor.ratio,
                attack_ms=compressor.attack_ms,
                release_ms=compressor.release_ms,
            )
        ]
    )


def _build_limiter_board() -> pedalboard.Pedalboard:
    # 全プリセット共通の安全弁。ceilingは-1.0dBFSでDiscord側のクリップを防ぐ(仕様書参照)。
    return pedalboard.Pedalboard(
        [pedalboard.Limiter(threshold_db=presets.LIMITER_CEILING_DBFS, release_ms=100.0)]
    )


class VoiceChain:
    """マイク入力1フレーム分の音声処理をまとめて呼べるDSPチェーン。"""

    def __init__(
        self,
        preset_name: str = presets.DEFAULT_PRESET,
        rnnoise_library_path: Optional[str] = None,
    ):
        self._rnnoise_library = rnnoise_mod.RNNoiseLibrary(rnnoise_library_path)
        self._rnnoise_state = rnnoise_mod.RNNoiseState(self._rnnoise_library)

        self._highpass_board: pedalboard.Pedalboard
        self._eq_board: pedalboard.Pedalboard
        self._compressor_board: pedalboard.Pedalboard
        self._limiter_board = _build_limiter_board()
        self._noise_stage: presets.NoiseStage
        self.gate: SpeechProbabilityGate
        self.agc: AutomaticGainControl

        self.clarity_level = presets.PRESETS[preset_name].clarity
        self.noise_level = presets.PRESETS[preset_name].noise
        self.preset_name = preset_name
        self.set_preset(preset_name)

    def set_preset(self, preset_name: str) -> None:
        preset = presets.PRESETS[preset_name]
        self.preset_name = preset_name
        self.set_clarity(preset.clarity)
        self.set_noise(preset.noise)
        self.set_compressor(preset.compressor)
        self.set_agc(preset.agc)

    def set_clarity(self, level: str) -> None:
        self.clarity_level = level
        self.set_clarity_stage(presets.CLARITY_STAGES[level])

    def set_clarity_stage(self, stage: presets.ClarityStage) -> None:
        """詳細設定パネルからの生値上書き用。プリセット段階に紐づかない値も渡せる。"""
        self._highpass_board = _build_highpass_board(stage.highpass_hz)
        self._eq_board = _build_eq_board(stage.bands)

    def set_noise(self, level: str) -> None:
        self.noise_level = level
        self.set_noise_stage(presets.NOISE_STAGES[level])

    def set_noise_stage(self, stage: presets.NoiseStage) -> None:
        """詳細設定パネルからの生値上書き用。"""
        self._noise_stage = stage
        self.gate = SpeechProbabilityGate(
            threshold=stage.gate_threshold, release_ms=stage.gate_release_ms
        )

    def set_compressor(self, compressor: presets.CompressorParams) -> None:
        self._compressor_board = _build_compressor_board(compressor)

    def set_agc(self, agc: presets.AgcParams) -> None:
        self.agc = AutomaticGainControl(
            target_dbfs=agc.target_dbfs,
            max_gain_db=agc.max_gain_db,
            attack_seconds=agc.attack_seconds,
            release_seconds=agc.release_seconds,
        )

    def process(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        """480サンプルのfloat32 mono(-1.0..1.0)を処理する。

        Returns:
            (処理後フレーム, RNNoiseが返した発話確率0.0-1.0)
        """
        assert frame.shape == (FRAME_SIZE,), f"frame must be shape ({FRAME_SIZE},), got {frame.shape}"
        assert frame.dtype == np.float32, f"frame dtype must be float32, got {frame.dtype}"

        highpassed = self._highpass_board.process(frame, SAMPLE_RATE, reset=False)

        pcm16_scale = rnnoise_mod.float32_to_pcm16_scale(highpassed)
        denoised_pcm16, speech_prob = self._rnnoise_state.process(pcm16_scale)
        denoised = rnnoise_mod.pcm16_scale_to_float32(denoised_pcm16)

        mix = self._noise_stage.wet_dry_mix
        blended = denoised * mix + highpassed * (1.0 - mix)

        eq_out = self._eq_board.process(blended, SAMPLE_RATE, reset=False)
        comp_out = self._compressor_board.process(eq_out, SAMPLE_RATE, reset=False)
        agc_out = self.agc.process(comp_out, speech_prob)
        limited = self._limiter_board.process(agc_out, SAMPLE_RATE, reset=False)
        gated = self.gate.apply(limited, speech_prob)

        return gated.astype(np.float32), speech_prob

    def close(self) -> None:
        self._rnnoise_state.close()

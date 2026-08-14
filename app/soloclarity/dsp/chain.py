"""1フレーム(480サンプル, 48kHz, float32 mono, -1.0..1.0)を処理するDSPチェーン。

信号処理チェーン(仕様書 D-001 / docs/tasks.md T-001準拠、D-012でwet/dry blendの
混合比計算をバックグラウンド/インパクト2系統へ拡張):
入力 -> HighpassFilter -> dry遅延バッファ(RNNoise出力遅延に整列) -> TransientDetector
     (整列後dryに対して混合比算出) -> RNNoise denoise(発話確率取得、wet/dry blend)
     -> EQ(PeakFilter束、明瞭度で強度可変) -> Compressor -> 自前AGC -> Limiter
     -> 発話確率ゲート -> 出力

D-015 Reviewer差し戻し(1巡目)対応: RNNoiseの入出力遅延について、旧実装(初回の
Step0-1実測)は「0サンプル」と結論しdry/wet整列を不要としていたが、この測定は
`RNNoiseState.process()`のin-place破壊的挙動によるテスト側のバグ(rnnoise.py
docstring参照)によるものだった。再測定(3つの独立した手法、
tests/test_rnnoise_wrapper.py参照)により、RNNoiseの出力は入力に対し
`rnnoise_mod.OUTPUT_DELAY_FRAMES`(2フレーム, 20ms)遅れることを確認した。
`process()`が返すdenoisedフレームは、その`OUTPUT_DELAY_FRAMES`フレーム前に
highpass後の信号として渡した内容に対応する。この時間差を無視してdenoisedと
現在のhighpassed(dry)を直接blendすると、0<mix<1の間コムフィルタ
(周期1/OUTPUT_DELAY_SAMPLES秒のノッチ列)が発生する。これを避けるため、
`VoiceChain`はdry信号(highpassed)を`OUTPUT_DELAY_FRAMES`フレーム分のバッファへ
通してから、対応する時刻のdenoised出力とblendする。TransientDetectorも
blendに使う整列後のdry信号に対して計算する(混合比の算出対象と実際に混合する
信号の時刻を一致させるため)。出力全体の遅延がOUTPUT_DELAY_FRAMES分
(20ms)追加される(docs/decisions.md D-015参照)。

発話状態(発話中か)の判定はSpeechActivityTracker(gate.py)へ一元化し、
AGC・ゲートの両方がこれを共有する。

D-015 Reviewer差し戻し(2巡目)対応: RNNoiseの`process()`が返す`speech_prob`は
denoisedオーディオと異なり遅延が無い(フレームnの入力に対するリアルタイムの推定値)。
一方AGC・ゲートが実際にゲイン制御を適用する対象はaligned_dry/denoised由来の
2フレーム前(n-DRY_DELAY_FRAMES)のオーディオである。整列前のspeech_probをそのまま
SpeechActivityTrackerへ渡すと、ゲート・AGCが「今処理中のオーディオ」より
DRY_DELAY_FRAMES分「未来」の発話確率で開閉・凍結判定をしてしまう
(ヒステリシス/hangoverのタイミングが本来より早くずれる)。これを避けるため、
speech_probもdry信号と同じ`DRY_DELAY_FRAMES`分の遅延バッファを通し、
SpeechActivityTrackerへ渡す前にオーディオパスと時間整列する。
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np
import pedalboard

from soloclarity import presets
from soloclarity.dsp import rnnoise as rnnoise_mod
from soloclarity.dsp.agc import AutomaticGainControl
from soloclarity.dsp.gate import SpeechActivityTracker, SpeechProbabilityGate
from soloclarity.dsp.transient import TransientDetector

FRAME_SIZE = rnnoise_mod.FRAME_SIZE
SAMPLE_RATE = rnnoise_mod.SAMPLE_RATE

# D-015: RNNoiseのdenoised出力は入力よりこのフレーム数だけ遅れる(実測値、
# rnnoise.OUTPUT_DELAY_FRAMES参照)。dry側をこのフレーム数だけ遅延させて整列する。
DRY_DELAY_FRAMES = rnnoise_mod.OUTPUT_DELAY_FRAMES

# D-015 Reviewer差し戻し(1巡目)対応で判明した副作用: dry/wet整列により、無音直後の
# 瞬間的なフルスケール立ち上がり(instant step transient)に対してpedalboard.Limiterの
# アタックが1フレーム分間に合わず、ceilingを超えるオーバーシュートを出すことがある
# (整列前は偶然タイミングがずれてこの弱点が露呈していなかっただけで、Limiter単体でも
# 再現する挙動。tests/test_chain.pyのtest_output_never_exceeds_limiter_ceiling参照)。
# Limiterは「Discord側のクリップを防ぐ安全弁」(モジュールdocstring参照)である以上、
# ceilingを実際に保証する必要があるため、Limiter出力に対する最終的なハードクリップを
# 安全網として追加する。
LIMITER_CEILING_LINEAR = 10.0 ** (presets.LIMITER_CEILING_DBFS / 20.0)


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
        [
            pedalboard.Limiter(
                threshold_db=presets.LIMITER_CEILING_DBFS,
                release_ms=presets.LIMITER_RELEASE_MS,
            )
        ]
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
        self._transient_detector = TransientDetector()
        # D-015: dry(highpassed)信号をRNNoiseの出力遅延ぶん遅延させ、denoisedと
        # 時間整列させるためのバッファ。無音で初期化する(起動直後の数フレームは
        # 整列先が無音になる=追加のstartup latencyだが、悪化ではなく既存のjitter
        # buffer primingと同種のトレードオフ)。
        self._dry_delay_buffer: deque[np.ndarray] = deque(
            (np.zeros(FRAME_SIZE, dtype=np.float32) for _ in range(DRY_DELAY_FRAMES)),
            maxlen=DRY_DELAY_FRAMES,
        )
        # D-015 Reviewer差し戻し(2巡目)対応: speech_probをaligned_dryと同じ遅延量で
        # 整列し、AGC・ゲートが参照する発話状態が「今処理中のオーディオ」に対応する
        # ようにする(無音相当の0.0で初期化)。
        self._speech_prob_delay_buffer: deque[float] = deque(
            (0.0 for _ in range(DRY_DELAY_FRAMES)),
            maxlen=DRY_DELAY_FRAMES,
        )

        self._highpass_board: pedalboard.Pedalboard
        self._eq_board: pedalboard.Pedalboard
        self._compressor_board: pedalboard.Pedalboard
        self._limiter_board = _build_limiter_board()
        self._noise_stage: presets.NoiseStage
        self.gate: Optional[SpeechProbabilityGate] = None
        self.agc: Optional[AutomaticGainControl] = None
        self.agc_params: Optional[presets.AgcParams] = None
        self._speech_tracker: Optional[SpeechActivityTracker] = None

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
        """詳細設定パネルからの生値上書き用。

        D-015: 呼び出しのたびにSpeechProbabilityGate/SpeechActivityTrackerを
        作り直すと、内部状態(ゲイン・hangoverカウンタ)がリセットされ、詳細設定
        スライダーを触るたびに声が一瞬消える副作用があった。既存インスタンスが
        あれば`set_params`で係数だけ更新し、状態は保持する。
        """
        self._noise_stage = stage
        if self.gate is None:
            self.gate = SpeechProbabilityGate(threshold=stage.gate_threshold, release_ms=stage.gate_release_ms)
        else:
            self.gate.set_params(threshold=stage.gate_threshold, release_ms=stage.gate_release_ms)
        if self._speech_tracker is None:
            self._speech_tracker = SpeechActivityTracker(open_threshold=stage.gate_threshold)
        else:
            self._speech_tracker.set_params(open_threshold=stage.gate_threshold)

    def set_compressor(self, compressor: presets.CompressorParams) -> None:
        self._compressor_board = _build_compressor_board(compressor)

    def set_agc(self, agc: presets.AgcParams) -> None:
        """D-015: 既存のAutomaticGainControlインスタンスがあれば`set_params`で
        係数だけ更新し、ゲイン・RMSエンベロープ等の内部状態は保持する
        (set_noise_stageと同じ理由)。"""
        self.agc_params = agc
        if self.agc is None:
            self.agc = AutomaticGainControl(
                target_dbfs=agc.target_dbfs,
                max_gain_db=agc.max_gain_db,
                attack_seconds=agc.attack_seconds,
                release_seconds=agc.release_seconds,
            )
        else:
            self.agc.set_params(
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

        # D-015: denoised(このprocess()呼び出しの戻り値)はDRY_DELAY_FRAMES前に
        # highpassedとして渡した信号に対応する。dry側を同じ時刻へ整列させてから
        # blendする(コムフィルタの回帰テスト: tests/test_chain.py参照)。
        aligned_dry = self._dry_delay_buffer.popleft()
        self._dry_delay_buffer.append(highpassed)

        # D-015 Reviewer差し戻し(2巡目)対応: speech_prob(遅延無し、フレームnの
        # リアルタイム推定値)をaligned_dryと同じDRY_DELAY_FRAMES分遅延させ、
        # SpeechActivityTrackerへ渡す発話状態がaligned_dry由来のオーディオ(n-2)と
        # 同じ時刻を指すようにする。戻り値のspeech_probは呼び出し元の一貫性のため
        # RNNoiseの生値のまま返す(ドキュメント通り「RNNoiseが返した発話確率」)。
        aligned_speech_prob = self._speech_prob_delay_buffer.popleft()
        self._speech_prob_delay_buffer.append(speech_prob)

        transient_score = self._transient_detector.process(aligned_dry)

        mix = self._noise_stage.background_wet_dry_mix * (1.0 - transient_score) + (
            self._noise_stage.impact_wet_dry_mix * transient_score
        )
        blended = denoised * mix + aligned_dry * (1.0 - mix)

        eq_out = self._eq_board.process(blended, SAMPLE_RATE, reset=False)
        comp_out = self._compressor_board.process(eq_out, SAMPLE_RATE, reset=False)
        speech_active = self._speech_tracker.update(aligned_speech_prob)
        agc_out = self.agc.process(comp_out, speech_active)
        limited = self._limiter_board.process(agc_out, SAMPLE_RATE, reset=False)
        limited = np.clip(limited, -LIMITER_CEILING_LINEAR, LIMITER_CEILING_LINEAR)
        gated = self.gate.apply(limited, speech_active)

        return gated.astype(np.float32), speech_prob

    def close(self) -> None:
        self._rnnoise_state.close()

"""VoiceChainの各段階の効果を、合成信号(低い声のモデル/小さい声のモデル/ホワイトノイズ)に対して
数値で検証する。

低い声のモデル: 100-150Hzのsin波+倍音(声の基本周波数帯)
小さい声のモデル: 振幅の小さい(peak -30dBFS相当)合成音
定常ノイズのモデル: ホワイトノイズ
"""

from __future__ import annotations

import numpy as np
import pytest

from soloclarity.dsp import chain as chain_mod
from soloclarity.dsp.chain import FRAME_SIZE, SAMPLE_RATE, VoiceChain
from soloclarity import presets


def make_low_voice_signal(n_samples: int, sr: int = SAMPLE_RATE, f0: float = 130.0, amplitude: float = 0.2, n_harmonics: int = 30) -> np.ndarray:
    """低い声を模した信号: 基本周波数f0(100-150Hz帯)とその倍音を1/hで減衰させて合成する。"""
    t = np.arange(n_samples) / sr
    sig = np.zeros(n_samples)
    for h in range(1, n_harmonics + 1):
        sig += (1.0 / h) * np.sin(2 * np.pi * f0 * h * t)
    sig = sig / np.max(np.abs(sig)) * amplitude
    return sig.astype(np.float32)


def band_energy(signal: np.ndarray, sr: int, low_hz: float, high_hz: float) -> float:
    spectrum = np.abs(np.fft.rfft(signal))
    freqs = np.fft.rfftfreq(len(signal), 1.0 / sr)
    mask = (freqs >= low_hz) & (freqs < high_hz)
    return float(np.sum(spectrum[mask] ** 2))


@pytest.fixture
def chain_factory(rnnoise_library_path):
    created = []

    def _factory(preset_name: str = presets.DEFAULT_PRESET) -> VoiceChain:
        chain = VoiceChain(preset_name, rnnoise_library_path=rnnoise_library_path)
        created.append(chain)
        return chain

    yield _factory
    for c in created:
        c.close()


class TestClarityEq:
    """明瞭度(EQ)の効果をFFTで検証する。

    RNNoise/Compressor/AGC/Limiterは全帯域に一様なゲイン(スカラー)しかかけない
    処理のため、HighpassFilter+PeakFilter(EQ)部分だけを取り出して検証すれば、
    元の合成信号に対する2帯域の相対的な変化(EQの効果そのもの)を正しく確認できる。
    """

    @pytest.mark.parametrize(
        "level",
        ["weak", "standard", "strong"],
    )
    def test_low_band_decreases_and_high_band_increases(self, level):
        sr = SAMPLE_RATE
        raw = make_low_voice_signal(sr * 3, sr=sr)

        stage = presets.CLARITY_STAGES[level]
        board = chain_mod._build_highpass_board(stage.highpass_hz)
        eq_board = chain_mod._build_eq_board(stage.bands)
        processed = eq_board.process(board.process(raw, sr), sr)

        low_in = band_energy(raw, sr, 200, 300)
        low_out = band_energy(processed, sr, 200, 300)
        high_in = band_energy(raw, sr, 2000, 4000)
        high_out = band_energy(processed, sr, 2000, 4000)

        assert low_out < low_in, f"{level}: 200-300Hz band should decrease vs original"
        assert high_out > high_in, f"{level}: 2-4kHz band should increase vs original"

    def test_strong_shapes_more_aggressively_than_weak(self):
        sr = SAMPLE_RATE
        raw = make_low_voice_signal(sr * 3, sr=sr)

        def low_high_ratio(level: str) -> tuple[float, float]:
            stage = presets.CLARITY_STAGES[level]
            board = chain_mod._build_highpass_board(stage.highpass_hz)
            eq_board = chain_mod._build_eq_board(stage.bands)
            processed = eq_board.process(board.process(raw, sr), sr)
            low_ratio = band_energy(processed, sr, 200, 300) / band_energy(raw, sr, 200, 300)
            high_ratio = band_energy(processed, sr, 2000, 4000) / band_energy(raw, sr, 2000, 4000)
            return low_ratio, high_ratio

        weak_low, weak_high = low_high_ratio("weak")
        strong_low, strong_high = low_high_ratio("strong")

        assert strong_low < weak_low  # 強のほうがより低域を削る
        assert strong_high > weak_high  # 強のほうがより高域を持ち上げる


class TestCompressorAgcLimiter:
    def test_output_never_exceeds_limiter_ceiling(self, chain_factory):
        chain = chain_factory("discord_call")
        ceiling_linear = 10 ** (presets.LIMITER_CEILING_DBFS / 20.0)

        peak_out = 0.0
        # 無音のウォームアップ後に急に大振幅の音が来るケース(AGCが追従する前の瞬間)を含める
        for i in range(30):
            frame = np.zeros(FRAME_SIZE, dtype=np.float32)
            out, _ = chain.process(frame)
            peak_out = max(peak_out, float(np.max(np.abs(out))))
        for i in range(30, 90):
            t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / SAMPLE_RATE
            frame = (0.999 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
            out, _ = chain.process(frame)
            peak_out = max(peak_out, float(np.max(np.abs(out))))

        assert peak_out <= ceiling_linear + 1e-6

    def test_quiet_signal_makes_agc_gain_increase_within_the_chain(self, chain_factory):
        """振幅の小さい合成音(peak -30dBFS相当)に対し、チェーン内のAGCゲインが
        target_dbfsへ近づく方向(増加方向)に働くことを確認する。

        RMSレベルそのものがtargetへ近づくことの数値検証はAGC単体のtest_agc.pyで
        厳密に行う(test_agc_raises_quiet_signal_toward_target)。チェーン全体を
        通すと、RNNoiseは合成トーンの周期的な性質を段々「非音声」寄りと判定して
        フレームごとの出力振幅が大きく揺らぐため、出力RMSそのものは単調に増加せず
        AGCの効果がRNNoiseの揺らぎに埋もれてしまう。AGCの内部ゲイン状態を見ることで、
        チェーンに正しく組み込まれ、量の小さい入力に対してゲインを上げる方向に
        反応していることを確認する。
        """
        chain = chain_factory("quiet_voice")
        amplitude = 10 ** (-30.0 / 20.0)  # peak -30dBFS相当

        initial_gain = chain.agc._gain
        n_frames = 80  # RNNoiseの発話確率がまだ高い区間(仕様書のゲート閾値0.30を上回る間)
        for i in range(n_frames):
            t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / SAMPLE_RATE
            frame = (amplitude * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
            chain.process(frame)

        assert chain.agc._gain > initial_gain
        assert chain.agc._gain <= chain.agc.max_gain_linear + 1e-9


class TestNoiseGateOnWhiteNoise:
    def test_white_noise_is_attenuated_by_full_chain(self, chain_factory):
        """ホワイトノイズのみ(無音相当、発話確率が低いはず)に対し、チェーン全体が減衰させる。"""
        chain = chain_factory("discord_call")
        rng = np.random.default_rng(5)

        in_energy = 0.0
        out_energy = 0.0
        for _ in range(300):
            frame = rng.normal(0.0, 0.05, FRAME_SIZE).astype(np.float32)
            out, _ = chain.process(frame)
            in_energy += float(np.sum(frame**2))
            out_energy += float(np.sum(out**2))

        assert out_energy < in_energy * 0.3


class TestChainSanity:
    @pytest.mark.parametrize("preset_name", list(presets.PRESET_ORDER))
    def test_process_runs_for_every_preset(self, chain_factory, preset_name):
        chain = chain_factory(preset_name)
        for i in range(10):
            t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / SAMPLE_RATE
            frame = (0.1 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
            out, speech_prob = chain.process(frame)
            assert out.shape == (FRAME_SIZE,)
            assert out.dtype == np.float32
            assert 0.0 <= speech_prob <= 1.0

    def test_wrong_frame_size_raises(self, chain_factory):
        chain = chain_factory()
        with pytest.raises(AssertionError):
            chain.process(np.zeros(100, dtype=np.float32))

    def test_wrong_dtype_raises(self, chain_factory):
        chain = chain_factory()
        with pytest.raises(AssertionError):
            chain.process(np.zeros(FRAME_SIZE, dtype=np.float64))


class TestHighFrequencyParameterSwitching:
    """プリセット・詳細設定の高頻度切り替えでも例外が出ず、RNNoiseのネイティブ状態が
    再作成されない(リークしない)ことを確認する。"""

    def test_rapid_random_switching_does_not_raise_and_keeps_rnnoise_state(self, chain_factory):
        chain = chain_factory("discord_call")
        original_rnnoise_state = chain._rnnoise_state
        original_rnnoise_library = chain._rnnoise_library
        rng = np.random.default_rng(3)

        def _random_preset():
            chain.set_preset(str(rng.choice(list(presets.PRESET_ORDER))))

        def _random_clarity():
            chain.set_clarity(str(rng.choice(list(presets.CLARITY_LEVELS))))

        def _random_noise():
            chain.set_noise(str(rng.choice(list(presets.NOISE_LEVELS))))

        def _random_compressor():
            chain.set_compressor(
                presets.CompressorParams(
                    threshold_db=float(rng.uniform(-40, 0)),
                    ratio=float(rng.uniform(1, 10)),
                    attack_ms=float(rng.uniform(1, 50)),
                    release_ms=float(rng.uniform(50, 500)),
                )
            )

        def _random_agc():
            chain.set_agc(
                presets.AgcParams(
                    target_dbfs=float(rng.uniform(-30, -6)),
                    max_gain_db=float(rng.uniform(0, 24)),
                )
            )

        setters = [_random_preset, _random_clarity, _random_noise, _random_compressor, _random_agc]

        for _ in range(3000):
            setters[rng.integers(0, len(setters))]()

        # RNNoiseのネイティブハンドルは__init__時の1回だけ作られ、set_preset等の
        # 呼び出しでは再作成されない(再作成されるとrnnoise_destroyされないネイティブ
        # ハンドルがリークする)。
        assert chain._rnnoise_state is original_rnnoise_state
        assert chain._rnnoise_library is original_rnnoise_library

        # 切り替え後もprocess()が正常に動くこと。
        t = np.arange(FRAME_SIZE) / SAMPLE_RATE
        frame = (0.1 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
        out, speech_prob = chain.process(frame)
        assert out.shape == (FRAME_SIZE,)
        assert out.dtype == np.float32
        assert 0.0 <= speech_prob <= 1.0


class TestCompressorSmoothness:
    """コンプレッサーが音量の急変(小->大->小)を、無加工の生信号より滑らかにすることを確認する。"""

    def test_compressor_does_not_amplify_volume_jumps(self):
        sr = SAMPLE_RATE
        amplitudes = [0.05] * 40 + [0.5] * 40 + [0.05] * 40

        raw_frames = []
        for i, amp in enumerate(amplitudes):
            t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / sr
            raw_frames.append((amp * np.sin(2 * np.pi * 200 * t)).astype(np.float32))
        raw = np.concatenate(raw_frames)

        preset = presets.PRESETS["discord_call"]
        board = chain_mod._build_compressor_board(preset.compressor)
        processed = board.process(raw, sr)

        def frame_rms_db_series(signal: np.ndarray) -> list[float]:
            values = []
            for i in range(0, len(signal), FRAME_SIZE):
                chunk = signal[i : i + FRAME_SIZE]
                r = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
                values.append(20.0 * np.log10(max(r, 1e-9)))
            return values

        raw_db = frame_rms_db_series(raw)
        out_db = frame_rms_db_series(processed)

        raw_max_jump = max(abs(b - a) for a, b in zip(raw_db, raw_db[1:]))
        out_max_jump = max(abs(b - a) for a, b in zip(out_db, out_db[1:]))

        assert out_max_jump <= raw_max_jump + 1e-6


class TestLimiterEngagementFrequency:
    """通常の音量範囲(クリップしない入力)ではリミッターがほぼ発動しないことを確認する。"""

    def test_limiter_barely_attenuates_normal_level_signal(self):
        sr = SAMPLE_RATE
        amplitude = 10 ** (-10.0 / 20.0)  # peak -10dBFS(ceiling -1.0dBFSより十分低い)

        frames = []
        for i in range(50):
            t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / sr
            frames.append((amplitude * np.sin(2 * np.pi * 200 * t)).astype(np.float32))
        raw = np.concatenate(frames)

        board = chain_mod._build_limiter_board()
        out = board.process(raw, sr)

        # 最初のフレーム(リミッターのウォームアップ)を除いた区間で比較する。
        warm_raw = raw[FRAME_SIZE:]
        warm_out = out[FRAME_SIZE:]
        raw_rms = float(np.sqrt(np.mean(warm_raw.astype(np.float64) ** 2)))
        out_rms = float(np.sqrt(np.mean(warm_out.astype(np.float64) ** 2)))

        assert out_rms / raw_rms > 0.98

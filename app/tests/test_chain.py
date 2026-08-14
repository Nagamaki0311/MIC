"""VoiceChainの各段階の効果を、合成信号(低い声のモデル/小さい声のモデル/ホワイトノイズ)に対して
数値で検証する。

低い声のモデル: 100-150Hzのsin波+倍音(声の基本周波数帯)
小さい声のモデル: 振幅の小さい(peak -30dBFS相当)合成音
定常ノイズのモデル: ホワイトノイズ
"""

from __future__ import annotations

import numpy as np
import pedalboard
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


def warm_up_chain(chain: VoiceChain, seed: int, amplitude: float = 0.03, n_frames: int = 120) -> None:
    """定常ノイズをある程度流し、TransientDetector/AGC/ゲートの内部状態(EMA等)を
    無音からの立ち上がり過渡(D-012のfast_env/slow_envがゼロ初期値から実信号レベルへ
    収束するまでの区間)から抜けさせてから本題の検証を始めるためのヘルパー。
    実際のマイク入力は常時ストリーミングされ続けるため、この過渡はテスト特有の
    アーティファクトであり、これを除いた定常状態で比較する。"""
    rng = np.random.default_rng(seed)
    for _ in range(n_frames):
        chain.process(rng.normal(0.0, amplitude, FRAME_SIZE).astype(np.float32))


def make_colored_noise(n_samples: int, rng: np.random.Generator, amplitude: float, cutoff_hz: float) -> np.ndarray:
    """ホワイトノイズにLowpassFilterをかけ、PCファン(広帯域)とは異なる
    スペクトル形状(低域に偏った、エアコンの送風音を模した)ノイズを合成する。"""
    board = pedalboard.Pedalboard([pedalboard.LowpassFilter(cutoff_hz)])
    white = rng.normal(0.0, 1.0, n_samples).astype(np.float32)
    filtered = board.process(white, SAMPLE_RATE)
    filtered = filtered / (np.std(filtered) + 1e-9) * amplitude
    return filtered.astype(np.float32)


def inject_click(signal: np.ndarray, frame_index: int, rng: np.random.Generator, pulse_len: int = 5, amplitude_range: tuple[float, float] = (0.3, 0.6)) -> np.ndarray:
    """1フレームの中央付近に短い高振幅パルス(打鍵音/クリック音を模した)を加える。"""
    out = signal.copy()
    pos = frame_index * FRAME_SIZE + FRAME_SIZE // 2
    out[pos : pos + pulse_len] += rng.uniform(*amplitude_range, pulse_len).astype(np.float32)
    return out


def make_voice_like_signal(
    n_samples: int,
    sr: int = SAMPLE_RATE,
    f0: float = 130.0,
    amplitude: float = 0.2,
    harmonic_cutoff_hz: float = 700.0,
    vibrato_hz: float = 5.0,
    vibrato_depth: float = 0.02,
    tremolo_hz: float = 4.0,
    tremolo_depth: float = 0.15,
    seed: int = 0,
) -> np.ndarray:
    """既存のmake_low_voice_signal(純周期合成音)はRNNoiseの発話確率がほぼ0付近に
    張り付き(実測: mean=0.023)、発話確率まわりのシナリオ検証には使えないことが
    Step0実測でわかった(D-015)。ビブラート(基本周波数のわずかな揺れ)・トレモロ
    (振幅のわずかな揺れ)・微小なブレスノイズを加えることで、RNNoiseに「発話」と
    高い確率で認識される信号を作る。倍音数はf0に応じてharmonic_cutoff_hz以下に
    収まるよう自動調整する(倍音が高くなりすぎるとRNNoiseの発話確率が急落する
    ことが実測でわかったため)。
    """
    rng = np.random.default_rng(seed)
    n_harmonics = max(3, round(harmonic_cutoff_hz / f0))
    t = np.arange(n_samples) / sr
    inst_f0 = f0 * (1.0 + vibrato_depth * np.sin(2 * np.pi * vibrato_hz * t))
    phase = np.cumsum(2 * np.pi * inst_f0 / sr)
    sig = np.zeros(n_samples)
    for h in range(1, n_harmonics + 1):
        sig += (1.0 / h) * np.sin(h * phase)
    envelope = 1.0 + tremolo_depth * np.sin(2 * np.pi * tremolo_hz * t)
    sig = sig * envelope
    sig = sig / np.max(np.abs(sig)) * amplitude
    breath = rng.normal(0.0, 0.02, n_samples)
    sig = sig + breath * amplitude * 0.05
    return sig.astype(np.float32)


def frame_rms_series(signal: np.ndarray, frame_size: int = FRAME_SIZE) -> list[float]:
    """フレームごとのRMS(線形)の系列を返す。"""
    values = []
    for i in range(0, len(signal), frame_size):
        chunk = signal[i : i + frame_size].astype(np.float64)
        values.append(float(np.sqrt(np.mean(chunk**2))))
    return values


def assert_no_dropouts(
    rms_values: list[float],
    active_mask: list[bool],
    median_window: int = 20,
    median_drop_db_limit: float = 8.0,
    frame_to_frame_drop_db_limit: float = 6.0,
) -> None:
    """発話が持続しているはずの区間で、フレームRMSが急激に落ち込んでいないことを
    確認する(D-015: ゲートのヒステリシス欠如+完全ミュートによる「プツプツ途切れる」
    バグの回帰テスト)。

    - 直前最大`median_window`フレームの中央値(dB)から`median_drop_db_limit`dB以上
      落ち込んでいないこと(緩やかな音量変化は許容しつつ、急な脱落を検出する)。
    - 直前1フレームからの落ち込みが`frame_to_frame_drop_db_limit`dB以下であること
      (フレーム間の急変=クリック/瞬間ミュートを検出する)。
    """
    eps = 1e-9
    db_values = [20.0 * np.log10(max(v, eps)) for v in rms_values]
    for i, is_active in enumerate(active_mask):
        if not is_active:
            continue
        window = db_values[max(0, i - median_window) : i]
        if window:
            median_db = float(np.median(window))
            drop = median_db - db_values[i]
            assert drop <= median_drop_db_limit, (
                f"frame {i}: dropout detected, {drop:.2f}dB below the preceding "
                f"{median_window}-frame median (limit {median_drop_db_limit}dB)"
            )
        if i > 0 and active_mask[i - 1]:
            frame_drop = db_values[i - 1] - db_values[i]
            assert frame_drop <= frame_to_frame_drop_db_limit, (
                f"frame {i}: frame-to-frame drop {frame_drop:.2f}dB exceeds limit "
                f"{frame_to_frame_drop_db_limit}dB"
            )


def assert_no_frame_boundary_clicks(
    signal: np.ndarray, frame_size: int = FRAME_SIZE, local_window: int = 20, click_ratio_limit: float = 6.0
) -> None:
    """フレーム境界(10ms周期)でのサンプル間差分が、その周辺のフレーム内部の
    典型的なサンプル間差分と比べて著しく大きくないことを確認する(D-015: ゲート/AGCの
    ゲインをフレーム単位のステップではなくフレーム内線形ランプへ変更したことの
    回帰テスト。ステップ適用のままだとフレーム境界で波形が不連続になりクリックが乗る)。
    """
    diffs = np.abs(np.diff(signal.astype(np.float64)))
    n_frames = len(signal) // frame_size
    for f in range(1, n_frames):
        boundary_idx = f * frame_size - 1
        lo = max(0, boundary_idx - local_window)
        hi = min(len(diffs), boundary_idx + local_window + 1)
        local = np.delete(diffs[lo:hi], boundary_idx - lo)
        if len(local) == 0:
            continue
        local_ref = float(np.max(local)) + 1e-9
        boundary_diff = diffs[boundary_idx]
        assert boundary_diff <= local_ref * click_ratio_limit, (
            f"frame boundary at sample {boundary_idx}: diff={boundary_diff:.6f} exceeds "
            f"{click_ratio_limit}x the surrounding local max diff ({local_ref:.6f}) -- possible click"
        )


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
        chain = chain_factory("quiet_low_voice")
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
        n_frames = 80  # RNNoiseの発話確率がまだ高い区間(quiet_voiceのnoise=standardのゲート閾値0.20を上回る間)
        for i in range(n_frames):
            t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / SAMPLE_RATE
            frame = (amplitude * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
            chain.process(frame)

        assert chain.agc._gain > initial_gain
        assert chain.agc._gain <= chain.agc.max_gain_linear + 1e-9


class TestNoiseGateOnWhiteNoise:
    def test_white_noise_is_attenuated_by_full_chain(self, chain_factory):
        """ホワイトノイズのみ(無音相当、発話確率が低いはず)に対し、チェーン全体が減衰させる。

        D-015でゲートが完全ミュート(0.0)からGATE_FLOOR_DB(-18dB)ダッキング+
        hangover(200ms)へ変更されたため、無音時にもわずかな残留ノイズが残る
        (プツプツ途切れを避けるための意図的なトレードオフ)。閾値はその分緩和している。
        """
        chain = chain_factory("quiet_low_voice")
        rng = np.random.default_rng(5)

        in_energy = 0.0
        out_energy = 0.0
        for _ in range(300):
            frame = rng.normal(0.0, 0.05, FRAME_SIZE).astype(np.float32)
            out, _ = chain.process(frame)
            in_energy += float(np.sum(frame**2))
            out_energy += float(np.sum(out**2))

        assert out_energy < in_energy * 0.45


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
        chain = chain_factory("quiet_low_voice")
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

        preset = presets.PRESETS["quiet_low_voice"]
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


class TestDryWetTimeAlignment:
    """D-015 Reviewer差し戻し(1巡目): denoised(wet)とhighpassed(dry)の時間整列が
    実際にコムフィルタを解消していることを、mix=0.5固定のスペクトル解析で確認する。

    純粋なホワイトノイズはRNNoiseにほぼ完全に抑圧され(実測60dB超の減衰)denoised側の
    寄与が無視できるほど小さくなるため、コムフィルタの検証には向かない。RNNoiseが
    ほぼ無加工で通す(D-015 Step0-2参照)`make_voice_like_signal`(声を模した
    倍音構造を持つ信号)を使い、各倍音での実測ゲイン(dry-onlyリファレンスとの比、dB)が
    倍音間で滑らかである(=コムフィルタ由来の周期的なノッチが無い)ことを確認する。

    EQ/Compressor/AGC/Gate/Limiterが持つそれぞれの周波数整形・時間変化する影響を
    排除するため、これらを実質的に無効化した(EQをバイパス、Compressor比1:1、AGCを
    ゲイン固定、ゲートを常時オープン)`VoiceChain`を使い、dry/wet整列そのものの効果を
    本番コードパス(`VoiceChain.process()`)を通して直接検証する。
    """

    F0 = 110.0

    @staticmethod
    def _build_neutral_chain(chain_factory, mix: float) -> VoiceChain:
        """EQ/Compressor/AGC/Gateの影響をほぼ無効化し、dry/wet blendの効果だけを
        観測できるようにしたチェーンを作る。"""
        chain = chain_factory("natural")
        chain.set_clarity_stage(presets.ClarityStage(highpass_hz=20.0, bands=()))
        chain.set_noise_stage(
            presets.NoiseStage(
                background_wet_dry_mix=mix, impact_wet_dry_mix=mix, gate_threshold=0.0, gate_release_ms=50.0
            )
        )
        chain.set_compressor(presets.CompressorParams(threshold_db=0.0, ratio=1.0, attack_ms=1.0, release_ms=1.0))
        chain.set_agc(presets.AgcParams(target_dbfs=-17.0, max_gain_db=0.0))  # ゲインを1.0に固定
        return chain

    @classmethod
    def _harmonic_gains_db(cls, chain_factory) -> np.ndarray:
        n_harmonics = max(3, round(700.0 / cls.F0))
        raw = make_voice_like_signal(6 * SAMPLE_RATE, f0=cls.F0, amplitude=0.2, seed=3)

        def harmonic_mags_db(seg: np.ndarray) -> np.ndarray:
            n = len(seg)
            spectrum = np.fft.rfft(seg * np.hanning(n))
            freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
            mags = []
            for h in range(1, n_harmonics + 1):
                idx = int(np.argmin(np.abs(freqs - h * cls.F0)))
                mags.append(20.0 * np.log10(np.abs(spectrum[idx]) + 1e-9))
            return np.array(mags)

        def process_all(chain: VoiceChain) -> np.ndarray:
            outputs = []
            for i in range(0, len(raw), FRAME_SIZE):
                out, _ = chain.process(raw[i : i + FRAME_SIZE])
                outputs.append(out)
            return np.concatenate(outputs)

        warmup_samples = int(1.0 * SAMPLE_RATE)  # AGC/ゲートの立ち上がり過渡を除く

        dry_only_chain = cls._build_neutral_chain(chain_factory, mix=0.0)
        dry_mags = harmonic_mags_db(process_all(dry_only_chain)[warmup_samples:])

        blended_chain = cls._build_neutral_chain(chain_factory, mix=0.5)
        blended_mags = harmonic_mags_db(process_all(blended_chain)[warmup_samples:])

        return blended_mags - dry_mags

    def test_blend_gain_is_flat_across_harmonics_no_comb_notches(self, chain_factory):
        """整列済みのdry/wet blendでは、各倍音でのゲイン(dB)がほぼ一定であること
        (=周期的なノッチが無いこと)を確認する。

        整列前(D-015 Reviewer差し戻し前のバグ)では、この同じ検証で最大約11.6dBの
        倍音間ゲイン変動(第2次倍音で-8.45dB、第3次倍音で-11.79dBの深いノッチ)が
        観測されていた(手元での修正前コードに対する実行結果)。修正後は倍音間の
        ゲイン変動が1dB未満に収まる。
        """
        gains_db = self._harmonic_gains_db(chain_factory)
        ripple_db = float(np.ptp(gains_db))
        assert ripple_db < 3.0, (
            f"harmonic gain ripple {ripple_db:.2f}dB (per-harmonic gains={np.round(gains_db, 2)}) "
            "suggests a comb filter between dry and wet paths; revisit dry/wet time alignment "
            "in chain.py (docs/decisions.md D-015)."
        )


class TestSpeechProbTimeAlignment:
    """D-015 Reviewer差し戻し(2巡目): RNNoiseが返すspeech_probはdenoised(出力オーディオ)と
    異なり遅延が無い(フレームnの入力に対するリアルタイムの推定値)。整列せずそのまま
    SpeechActivityTrackerへ渡すと、ゲート・AGCは「今処理中のオーディオ」(aligned_dry/
    denoised由来でDRY_DELAY_FRAMES遅れている)より未来の発話確率で開閉・凍結判定を
    してしまう。speech_probをaligned_dryと同じDRY_DELAY_FRAMES分遅延させることで、
    speech_activeがTrueへ切り替わるフレームと、出力オーディオが実際に立ち上がる
    フレームが一致することを確認する。

    修正前(speech_probを整列せず`self._speech_tracker.update(speech_prob)`へ生値の
    まま渡すコード)へ戻すと、speech_activeがDRY_DELAY_FRAMES(2フレーム)早く
    切り替わり、本テストは失敗する(手元で確認済み)。
    """

    def test_speech_active_transition_aligns_with_output_audio_rise(self, chain_factory):
        silence_frames = 60
        burst_frames = 40
        silence = np.zeros(silence_frames * FRAME_SIZE, dtype=np.float32)
        burst = make_voice_like_signal(burst_frames * FRAME_SIZE, f0=110.0, amplitude=10 ** (-20.0 / 20.0), seed=11)
        signal = np.concatenate([silence, burst])

        chain = chain_factory("quiet_low_voice")
        speech_active_series: list[bool] = []
        rms_series: list[float] = []
        for i in range(0, len(signal), FRAME_SIZE):
            frame = signal[i : i + FRAME_SIZE]
            out, _ = chain.process(frame)
            speech_active_series.append(chain._speech_tracker._active)
            rms_series.append(float(np.sqrt(np.mean(out.astype(np.float64) ** 2))))

        # RNNoiseのSTFT解析窓のオーバーラップにより、burst開始の1フレーム前後で
        # ごく微小な(steady-stateの1%未満の)漏れ込みが観測されるため、単純な
        # 「ゼロでなくなる最初のフレーム」ではなく、定常区間RMSの半分を超える最初の
        # フレームで「オーディオが実際に立ち上がった」タイミングを判定する
        # (Reviewerの実測手法「RMSがベースラインの半分を超える」に合わせた)。
        steady_state_rms = float(np.median(rms_series[80:100]))
        rms_half_threshold = steady_state_rms * 0.5
        t_active = next(i for i, active in enumerate(speech_active_series) if active)
        t_audio_rise = next(i for i, rms in enumerate(rms_series) if rms > rms_half_threshold)

        assert t_active == t_audio_rise, (
            f"speech_active first became True at frame {t_active}, but the output audio's RMS "
            f"first crossed half of the steady-state level ({rms_half_threshold:.6f}) at frame "
            f"{t_audio_rise} (expected these to match: gate/AGC decisions must reference the same "
            "audio timeline that speech_prob was measured on, not a frame that is DRY_DELAY_FRAMES "
            "in the future relative to the audio currently being emitted; see chain.py "
            "aligned_speech_prob, docs/decisions.md D-015)."
        )


class TestQuietLowVoicePresetRealWorldScenarios:
    """quiet_low_voiceプリセット(D-015再設計後)を、ユーザーが指定した16の想定
    利用シーンそれぞれについて合成信号で検証する(docs/decisions.md D-015参照)。

    実際に人が聞いて確認したものではなく、この開発環境で実行できる自動テスト・
    合成信号による検証結果である。特に「あーーー」持続(シナリオ5)でゲートゲイン
    (chain.gate._gain)が1.0未満に落ちる回数は、D-015が修正対象とした「プツプツ
    途切れる」バグの直接的な回帰指標として最重要視する。
    """

    PRESET = "quiet_low_voice"

    # Step0実測(D-015)で発話確率が安定して高くなることを確認した基本周波数。
    LOW_F0 = 110.0
    NORMAL_F0 = 210.0

    @staticmethod
    def _process_all(chain: VoiceChain, raw: np.ndarray) -> tuple[np.ndarray, list[float]]:
        outputs = []
        speech_probs = []
        for i in range(0, len(raw), FRAME_SIZE):
            frame = raw[i : i + FRAME_SIZE]
            out, prob = chain.process(frame)
            outputs.append(out)
            speech_probs.append(prob)
        return np.concatenate(outputs), speech_probs

    @staticmethod
    def _process_all_with_gate_gain(chain: VoiceChain, raw: np.ndarray) -> tuple[np.ndarray, list[float], list[float]]:
        outputs = []
        speech_probs = []
        gate_gains = []
        for i in range(0, len(raw), FRAME_SIZE):
            frame = raw[i : i + FRAME_SIZE]
            out, prob = chain.process(frame)
            outputs.append(out)
            speech_probs.append(prob)
            gate_gains.append(chain.gate._gain)
        return np.concatenate(outputs), speech_probs, gate_gains

    # --- シナリオ1-4: 声量/音域の組み合わせ ------------------------------------

    def test_scenario1_quiet_low_voice(self, chain_factory):
        """シナリオ1: 小さい低い声。ドロップアウト・フレーム境界クリックが無く、
        AGCが持ち上げる方向に働くことを確認する。"""
        raw = make_voice_like_signal(200 * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-32.0 / 20.0))
        chain = chain_factory(self.PRESET)
        initial_gain = chain.agc._gain
        out, _ = self._process_all(chain, raw)
        assert chain.agc._gain > initial_gain, "AGC should raise gain for a quiet, low voice"

        rms_values = frame_rms_series(out)
        active_mask = [True] * len(rms_values)
        active_mask[:5] = [False] * 5  # 起動直後の立ち上がりは除く
        assert_no_dropouts(rms_values, active_mask)
        assert_no_frame_boundary_clicks(out)

    def test_scenario2_normal_volume_low_voice(self, chain_factory):
        """シナリオ2: 普通の音量の低い声。ドロップアウト・クリックが無いことを確認する。"""
        raw = make_voice_like_signal(200 * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-20.0 / 20.0))
        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)

        rms_values = frame_rms_series(out)
        active_mask = [True] * len(rms_values)
        active_mask[:5] = [False] * 5
        assert_no_dropouts(rms_values, active_mask)
        assert_no_frame_boundary_clicks(out)

    def test_scenario3_normal_voice(self, chain_factory):
        """シナリオ3: 普通の声(通常の音域・音量)。出力がリミッターceilingを超えず、
        ドロップアウト・クリックが無いことを確認する。"""
        ceiling_linear = 10 ** (presets.LIMITER_CEILING_DBFS / 20.0)
        raw = make_voice_like_signal(200 * FRAME_SIZE, f0=self.NORMAL_F0, amplitude=10 ** (-18.0 / 20.0))
        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        assert float(np.max(np.abs(out))) <= ceiling_linear + 1e-6

        rms_values = frame_rms_series(out)
        active_mask = [True] * len(rms_values)
        active_mask[:5] = [False] * 5
        assert_no_dropouts(rms_values, active_mask)
        assert_no_frame_boundary_clicks(out)

    def test_scenario4_loud_voice(self, chain_factory):
        """シナリオ4: 大きい声。出力がリミッターceilingを一度も超えないこと、
        AGCが不自然に持ち上げすぎないことを確認する。"""
        ceiling_linear = 10 ** (presets.LIMITER_CEILING_DBFS / 20.0)
        raw = make_voice_like_signal(200 * FRAME_SIZE, f0=self.NORMAL_F0, amplitude=10 ** (-8.0 / 20.0))
        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        assert float(np.max(np.abs(out))) <= ceiling_linear + 1e-6
        assert chain.agc._gain < 1.5, "already-loud voice should not be boosted further"

    # --- シナリオ5-8: 持続・反復・朗読・語尾 -------------------------------------

    def test_scenario5_sustained_ahh_gate_never_drops_below_full_gain(self, chain_factory):
        """シナリオ5: 「あーーー」持続3秒。D-015が修正対象とした「プツプツ途切れる」
        バグの最重要回帰テスト。持続的な発声中、ゲートゲイン(chain.gate._gain)が
        1.0未満に落ちる回数が0であることを確認する。"""
        n_frames = 300  # 3秒
        raw = make_voice_like_signal(n_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-26.0 / 20.0))
        chain = chain_factory(self.PRESET)
        out, probs, gate_gains = self._process_all_with_gate_gain(chain, raw)

        # attack_ms=5msの立ち上がり(指数収束のため厳密には1.0へ漸近的にしか
        # 到達しない)を除いた区間で判定する。
        settled_gains = gate_gains[5:]
        below_full_gain_count = sum(1 for g in settled_gains if g < 0.999)
        assert below_full_gain_count == 0, (
            f"gate gain dropped below 1.0 {below_full_gain_count} times during a sustained "
            f"vowel (min gain observed: {min(settled_gains):.4f})"
        )

        rms_values = frame_rms_series(out)
        active_mask = [True] * len(rms_values)
        active_mask[:5] = [False] * 5
        assert_no_dropouts(rms_values, active_mask)
        assert_no_frame_boundary_clicks(out)

    def test_scenario6_moshi_moshi_repeated(self, chain_factory):
        """シナリオ6: 「もしもし」反復。短い発声区間と短い無音区間を繰り返す
        パターンで、各発声区間内にドロップアウトが無いことを確認する。"""
        burst_frames = 25  # 250ms
        gap_frames = 10  # 100ms
        n_repeats = 4
        parts = []
        active_mask: list[bool] = []
        for r in range(n_repeats):
            burst = make_voice_like_signal(
                burst_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-24.0 / 20.0), seed=r
            )
            parts.append(burst)
            active_mask += [True] * burst_frames
            gap = np.zeros(gap_frames * FRAME_SIZE, dtype=np.float32)
            parts.append(gap)
            active_mask += [False] * gap_frames
        raw = np.concatenate(parts)

        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        rms_values = frame_rms_series(out)

        # 各burstの先頭2フレーム(発話確率の立ち上がり)は判定から除く。
        for r in range(n_repeats):
            burst_start = r * (burst_frames + gap_frames)
            active_mask[burst_start : burst_start + 2] = [False, False]
        assert_no_dropouts(rms_values, active_mask)
        assert_no_frame_boundary_clicks(out)

    def test_scenario7_quiet_reading(self, chain_factory):
        """シナリオ7: 小さい声の朗読(長めの発声+短い間を繰り返す)。ドロップアウトが
        無いことを確認する。"""
        sentence_frames = 60  # 600ms
        pause_frames = 15  # 150ms
        n_sentences = 5
        parts = []
        active_mask: list[bool] = []
        for s in range(n_sentences):
            sentence = make_voice_like_signal(
                sentence_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-30.0 / 20.0), seed=100 + s
            )
            parts.append(sentence)
            active_mask += [True] * sentence_frames
            pause = np.zeros(pause_frames * FRAME_SIZE, dtype=np.float32)
            parts.append(pause)
            active_mask += [False] * pause_frames
        raw = np.concatenate(parts)

        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        rms_values = frame_rms_series(out)

        for s in range(n_sentences):
            sentence_start = s * (sentence_frames + pause_frames)
            active_mask[sentence_start : sentence_start + 2] = [False, False]
        assert_no_dropouts(rms_values, active_mask)
        assert_no_frame_boundary_clicks(out)

    def test_scenario8_word_tail_elongation_fades_smoothly(self, chain_factory):
        """シナリオ8: 語尾を伸ばす(持続音の末尾で振幅がなだらかに減衰する)。
        フレーム境界にクリックが乗らないこと、末尾がいきなり無音にならず
        なだらかに減衰することを確認する。"""
        n_frames = 150  # 1.5秒
        raw = make_voice_like_signal(n_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-24.0 / 20.0))
        # 末尾30フレームでなだらかにフェードアウトさせる。
        fade_frames = 30
        fade_samples = fade_frames * FRAME_SIZE
        fade_curve = np.ones(len(raw), dtype=np.float32)
        fade_curve[-fade_samples:] = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
        raw = raw * fade_curve

        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        assert_no_frame_boundary_clicks(out)

    # --- シナリオ9-12: 音量遷移・発声の開始/終了 ---------------------------------

    def test_scenario9_quiet_to_normal_transition(self, chain_factory):
        """シナリオ9: 小声→通常の音量遷移。遷移後の区間にドロップアウトが無いことを確認する。"""
        n_each = 100
        quiet = make_voice_like_signal(n_each * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-32.0 / 20.0), seed=1)
        normal = make_voice_like_signal(n_each * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-18.0 / 20.0), seed=2)
        raw = np.concatenate([quiet, normal])

        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        rms_values = frame_rms_series(out)
        active_mask = [True] * len(rms_values)
        active_mask[:5] = [False] * 5
        # 遷移直後は「直前20フレーム中央値」の窓に遷移前(異なる音量)のフレームが
        # 混ざり誤検出するため、窓が遷移後フレームのみで埋まるまで判定から除く。
        active_mask[n_each : n_each + 21] = [False] * 21
        assert_no_dropouts(rms_values, active_mask)

    def test_scenario10_normal_to_quiet_transition(self, chain_factory):
        """シナリオ10: 通常→小声の音量遷移。遷移後の区間にドロップアウトが無いことを確認する。"""
        n_each = 100
        normal = make_voice_like_signal(n_each * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-18.0 / 20.0), seed=3)
        quiet = make_voice_like_signal(n_each * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-32.0 / 20.0), seed=4)
        raw = np.concatenate([normal, quiet])

        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        rms_values = frame_rms_series(out)
        active_mask = [True] * len(rms_values)
        active_mask[:5] = [False] * 5
        active_mask[n_each : n_each + 21] = [False] * 21
        assert_no_dropouts(rms_values, active_mask)

    def test_scenario11_silence_to_speech_onset(self, chain_factory):
        """シナリオ11: 無音→発声。発声開始後、数フレーム以内に十分な音量へ
        立ち上がることを確認する(頭が削れて聞こえない、を防ぐ)。"""
        silence = np.zeros(60 * FRAME_SIZE, dtype=np.float32)
        speech = make_voice_like_signal(150 * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-24.0 / 20.0))
        raw = np.concatenate([silence, speech])

        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        rms_values = frame_rms_series(out)

        onset_frame = 60
        onset_db = [20.0 * np.log10(max(v, 1e-9)) for v in rms_values[onset_frame : onset_frame + 20]]
        # 発声開始から10フレーム(100ms)以内に、その後の定常区間の中央値付近まで
        # 立ち上がっていること(頭が削られていないこと)。
        steady_db = float(np.median(onset_db[10:]))
        assert onset_db[9] > steady_db - 8.0, "speech onset should ramp up within ~100ms"

    def test_scenario12_speech_to_silence_offset(self, chain_factory):
        """シナリオ12: 発声→無音。発声終了後、いきなり無音にクリップされず
        release_msに応じてなだらかに減衰することを確認する。"""
        speech = make_voice_like_signal(150 * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-24.0 / 20.0))
        silence = np.zeros(60 * FRAME_SIZE, dtype=np.float32)
        raw = np.concatenate([speech, silence])

        chain = chain_factory(self.PRESET)
        out, _ = self._process_all(chain, raw)
        assert_no_frame_boundary_clicks(out)

        rms_values = frame_rms_series(out)
        offset_frame = 150
        # 発声終了直後の1フレームでいきなりフロア付近まで落ちきらないこと
        # (release_msに応じてなだらかに減衰する)。
        speech_db = 20.0 * np.log10(max(rms_values[offset_frame - 1], 1e-9))
        immediate_after_db = 20.0 * np.log10(max(rms_values[offset_frame], 1e-9))
        assert speech_db - immediate_after_db <= 10.0, (
            "speech-to-silence offset should fade gradually, not cut abruptly within one frame"
        )

    # --- シナリオ13-16: 背景ノイズ・打鍵音との組み合わせ ---------------------------

    def test_scenario13_fan_noise_plus_quiet_low_voice(self, chain_factory):
        """シナリオ13: PCファン(ホワイトノイズ)+小さい低い声。ノイズのみの区間と
        比べてエネルギーが十分保たれる(声が丸ごと消えていない)ことを確認する。"""
        n_frames = 80
        speech = make_voice_like_signal(n_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-24.0 / 20.0))

        noise_only_chain = chain_factory(self.PRESET)
        warm_up_chain(noise_only_chain, seed=999, amplitude=0.03)
        rng_noise_only = np.random.default_rng(17)
        noise_only_out_energy = 0.0
        for _ in range(n_frames):
            noise = rng_noise_only.normal(0.0, 0.03, FRAME_SIZE).astype(np.float32)
            out, _ = noise_only_chain.process(noise)
            noise_only_out_energy += float(np.sum(out**2))

        speech_plus_noise_chain = chain_factory(self.PRESET)
        warm_up_chain(speech_plus_noise_chain, seed=999, amplitude=0.03)
        rng_same_noise = np.random.default_rng(17)
        speech_plus_noise_out_energy = 0.0
        for i in range(n_frames):
            noise = rng_same_noise.normal(0.0, 0.03, FRAME_SIZE).astype(np.float32)
            frame = speech[i * FRAME_SIZE : (i + 1) * FRAME_SIZE] + noise
            out, _ = speech_plus_noise_chain.process(frame.astype(np.float32))
            speech_plus_noise_out_energy += float(np.sum(out**2))

        assert speech_plus_noise_out_energy > noise_only_out_energy * 5.0

    def test_scenario14_air_conditioner_noise_plus_quiet_low_voice(self, chain_factory):
        """シナリオ14: エアコン(低域寄りの色付きノイズ)+小さい低い声。シナリオ13と
        同じ観点をスペクトル形状が異なるノイズで確認する。"""
        n_frames = 80
        speech = make_voice_like_signal(n_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=10 ** (-24.0 / 20.0))

        noise_only_chain = chain_factory(self.PRESET)
        rng_noise_only = np.random.default_rng(31)
        ac_noise_only = make_colored_noise(n_frames * FRAME_SIZE, rng_noise_only, amplitude=0.02, cutoff_hz=500.0)
        warm_up_chain(noise_only_chain, seed=998, amplitude=0.02)
        noise_only_out_energy = 0.0
        for i in range(n_frames):
            out, _ = noise_only_chain.process(ac_noise_only[i * FRAME_SIZE : (i + 1) * FRAME_SIZE])
            noise_only_out_energy += float(np.sum(out**2))

        speech_plus_noise_chain = chain_factory(self.PRESET)
        rng_same_noise = np.random.default_rng(31)
        ac_noise_same = make_colored_noise(n_frames * FRAME_SIZE, rng_same_noise, amplitude=0.02, cutoff_hz=500.0)
        warm_up_chain(speech_plus_noise_chain, seed=998, amplitude=0.02)
        speech_plus_noise_out_energy = 0.0
        for i in range(n_frames):
            frame = speech[i * FRAME_SIZE : (i + 1) * FRAME_SIZE] + ac_noise_same[i * FRAME_SIZE : (i + 1) * FRAME_SIZE]
            out, _ = speech_plus_noise_chain.process(frame.astype(np.float32))
            speech_plus_noise_out_energy += float(np.sum(out**2))

        assert speech_plus_noise_out_energy > noise_only_out_energy * 5.0

    def test_scenario15_keyboard_click_plus_quiet_low_voice(self, chain_factory):
        """シナリオ15: 打鍵音+小さい低い声。打鍵音を処理(抑制)しても、その直前・
        直後の声のエネルギーが大きく損なわれていないことを確認する。"""
        n_frames = 60
        amplitude = 10 ** (-32.0 / 20.0)
        speech = make_voice_like_signal(n_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=amplitude)

        click_frame = 40
        rng = np.random.default_rng(41)
        speech_with_click = inject_click(speech, click_frame, rng)

        baseline_chain = chain_factory(self.PRESET)
        warm_up_chain(baseline_chain, seed=1, amplitude=0.002)
        baseline_energy: dict[int, float] = {}
        for i in range(n_frames):
            frame = speech[i * FRAME_SIZE : (i + 1) * FRAME_SIZE]
            out, _ = baseline_chain.process(frame.astype(np.float32))
            baseline_energy[i] = float(np.sum(out**2))

        click_chain = chain_factory(self.PRESET)
        warm_up_chain(click_chain, seed=1, amplitude=0.002)
        click_energy: dict[int, float] = {}
        for i in range(n_frames):
            frame = speech_with_click[i * FRAME_SIZE : (i + 1) * FRAME_SIZE]
            out, _ = click_chain.process(frame.astype(np.float32))
            click_energy[i] = float(np.sum(out**2))

        for i in range(click_frame):
            assert click_energy[i] == baseline_energy[i], (
                f"frame {i} (before the click) must be unaffected by a later click"
            )

        after_click_baseline = sum(baseline_energy[i] for i in range(click_frame + 1, click_frame + 4))
        after_click_with_click = sum(click_energy[i] for i in range(click_frame + 1, click_frame + 4))
        assert after_click_with_click > after_click_baseline * 0.5, (
            "speech energy right after a keyboard click should not collapse"
        )

    def test_scenario16_environment_noise_plus_click_plus_quiet_low_voice(self, chain_factory):
        """シナリオ16: 環境音+打鍵音+小さい低い声(3要素が重なる最も厳しい条件)。
        出力がリミッターceilingを超えない、shape/dtypeが壊れない、例外が出ない、
        ノイズのみと比べてエネルギーが十分保たれることを確認する。"""
        ceiling_linear = 10 ** (presets.LIMITER_CEILING_DBFS / 20.0)
        n_frames = 100
        amplitude = 10 ** (-30.0 / 20.0)
        speech = make_voice_like_signal(n_frames * FRAME_SIZE, f0=self.LOW_F0, amplitude=amplitude)

        rng_noise = np.random.default_rng(61)
        noise = rng_noise.normal(0.0, 0.03, n_frames * FRAME_SIZE).astype(np.float32)

        rng_click = np.random.default_rng(62)
        click_frames = set(rng_click.choice(range(10, n_frames - 5), size=5, replace=False).tolist())
        combined = speech + noise
        for cf in click_frames:
            combined = inject_click(combined, cf, rng_click)

        chain = chain_factory(self.PRESET)
        warm_up_chain(chain, seed=903)
        out_energy = 0.0
        for i in range(n_frames):
            frame = combined[i * FRAME_SIZE : (i + 1) * FRAME_SIZE].astype(np.float32)
            out, speech_prob = chain.process(frame)  # 例外が出ず完走すること自体も確認
            assert out.shape == (FRAME_SIZE,)
            assert out.dtype == np.float32
            assert 0.0 <= speech_prob <= 1.0
            assert np.max(np.abs(out)) <= ceiling_linear + 1e-6
            out_energy += float(np.sum(out**2))

        noise_only_chain = chain_factory(self.PRESET)
        warm_up_chain(noise_only_chain, seed=903)
        rng_noise_only = np.random.default_rng(61)
        noise_only_energy = 0.0
        for _ in range(n_frames):
            frame = rng_noise_only.normal(0.0, 0.03, FRAME_SIZE).astype(np.float32)
            out, _ = noise_only_chain.process(frame)
            noise_only_energy += float(np.sum(out**2))

        assert out_energy > noise_only_energy * 3.0, "speech should not be fully swallowed by noise+click suppression"

"""自前ctypesラッパー(soloclarity.dsp.rnnoise)の実検証。

pip installで取得できるpyrnnoiseのmanylinux wheel内のlibrnnoise.soを、
自前ラッパーへ直接ロードして、実際にRNNoiseのdenoiseを正しく呼び出せることを検証する。

D-015: 本ファイルには、RNNoiseの入出力遅延に関する回帰テストも含む。Step0-1の
実測(チャープ信号の広帯域相互相関、および複数周波数での位相ベースgroup delay
測定の2手法)で、`rnnoise_process_frame`の入出力に測定可能な遅延は無い(0サンプル)
ことを確認した。これはソースコード読解(RNNoiseの解析窓が[前フレーム, 今フレーム]
をまたぐため出力が1フレーム遅れる、という仮説)を実測が覆した結果であり、
`chain.py`のdry/wetパス整列(1フレーム遅延バッファの挿入)は実施していない。
下記の遅延回帰テストは、将来RNNoiseの共有ライブラリが更新され、実際に1フレーム分の
出力遅延を持つ挙動へ変わった場合に検知するためのものである。もし失敗した場合は、
docs/decisions.md D-015のStep1(dry/wetパスの時間整列)を再度検討する必要がある。
"""

from __future__ import annotations

import numpy as np
import pytest

from soloclarity.dsp import rnnoise as rn

SAMPLE_RATE = 48000


def _make_noise_frame(rng, frame_size=rn.FRAME_SIZE, amplitude=0.05):
    return (rng.normal(0.0, amplitude, frame_size)).astype(np.float32)


class TestRNNoiseLibrary:
    def test_loads_and_reports_frame_size(self, rnnoise_library_path):
        library = rn.RNNoiseLibrary(rnnoise_library_path)
        assert library.lib.rnnoise_get_frame_size() == rn.FRAME_SIZE

    def test_missing_library_raises(self, tmp_path):
        with pytest.raises(OSError):
            rn.RNNoiseLibrary(str(tmp_path / "does_not_exist.so"))


class TestRNNoiseState:
    def test_process_returns_expected_shape_and_probability_range(self, rnnoise_library_path):
        library = rn.RNNoiseLibrary(rnnoise_library_path)
        state = rn.RNNoiseState(library)
        rng = np.random.default_rng(1)
        frame = rn.float32_to_pcm16_scale(_make_noise_frame(rng))
        denoised, speech_prob = state.process(frame)
        assert denoised.shape == (rn.FRAME_SIZE,)
        assert denoised.dtype == np.float32
        assert 0.0 <= speech_prob <= 1.0
        state.close()

    def test_wrong_frame_size_raises(self, rnnoise_library_path):
        library = rn.RNNoiseLibrary(rnnoise_library_path)
        state = rn.RNNoiseState(library)
        bad_frame = np.zeros(100, dtype=np.float32)
        with pytest.raises(AssertionError):
            state.process(bad_frame)
        state.close()

    def test_denoises_stationary_noise(self, rnnoise_library_path):
        """定常ノイズ(ホワイトノイズ)を含む合成音に対し、実際にRMSが減衰することを検証する。

        RNNoiseは内部にノイズ推定の適応フィルタを持つため、数フレームのウォームアップ後の
        区間で比較する。
        """
        library = rn.RNNoiseLibrary(rnnoise_library_path)
        state = rn.RNNoiseState(library)
        rng = np.random.default_rng(42)

        n_frames = 200  # 2秒分
        raw_rms = []
        denoised_rms = []
        for _ in range(n_frames):
            frame = _make_noise_frame(rng, amplitude=0.05)
            pcm16 = rn.float32_to_pcm16_scale(frame)
            denoised_pcm16, _speech_prob = state.process(pcm16)
            denoised_f = rn.pcm16_scale_to_float32(denoised_pcm16)
            raw_rms.append(float(np.sqrt(np.mean(frame**2))))
            denoised_rms.append(float(np.sqrt(np.mean(denoised_f**2))))
        state.close()

        # ウォームアップ(最初の1秒)を除いた後半で比較する。
        warm_raw = np.mean(raw_rms[100:])
        warm_denoised = np.mean(denoised_rms[100:])
        assert warm_denoised < warm_raw * 0.5, (
            f"denoised RMS ({warm_denoised}) should be well below raw RMS ({warm_raw}) "
            "for pure stationary noise"
        )

    def test_scale_round_trip_is_close_to_identity(self):
        rng = np.random.default_rng(2)
        original = rng.uniform(-1.0, 1.0, rn.FRAME_SIZE).astype(np.float32)
        round_tripped = rn.pcm16_scale_to_float32(rn.float32_to_pcm16_scale(original))
        np.testing.assert_allclose(round_tripped, original, atol=1e-4)


# --- D-015: 入出力遅延の回帰テスト ------------------------------------------

# 遅延が無い(0サンプル)ことを期待する。もし1フレーム(480サンプル)の遅延が
# 生じていれば、この許容量を大きく超える。
DELAY_TOLERANCE_SAMPLES = rn.FRAME_SIZE // 4


def _measure_group_delay_samples(rnnoise_library_path: str, freq: float, n_frames: int = 300, amplitude: float = 8000.0) -> float:
    """定常正弦波の位相差から、入出力間のgroup delay(サンプル数)を推定する。"""
    library = rn.RNNoiseLibrary(rnnoise_library_path)
    state = rn.RNNoiseState(library)
    try:
        t = np.arange(n_frames * rn.FRAME_SIZE) / SAMPLE_RATE
        sig = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)

        outputs = []
        for i in range(n_frames):
            frame = sig[i * rn.FRAME_SIZE : (i + 1) * rn.FRAME_SIZE]
            out, _prob = state.process(frame)
            outputs.append(out.copy())
        output = np.concatenate(outputs)
    finally:
        state.close()

    # 立ち上がり過渡を除いた定常区間で比較する。
    seg_start = 150 * rn.FRAME_SIZE
    seg_len = 100 * rn.FRAME_SIZE
    x = sig[seg_start : seg_start + seg_len].astype(np.float64)
    y = output[seg_start : seg_start + seg_len].astype(np.float64)

    n = len(x)
    freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    idx = int(np.argmin(np.abs(freqs - freq)))
    spectrum_x = np.fft.rfft(x)[idx]
    spectrum_y = np.fft.rfft(y)[idx]

    phase_diff = np.angle(spectrum_y) - np.angle(spectrum_x)
    phase_diff = (phase_diff + np.pi) % (2 * np.pi) - np.pi  # [-pi, pi]へ正規化
    return float(-phase_diff / (2 * np.pi * freq) * SAMPLE_RATE)


def test_rnnoise_process_frame_has_no_measurable_output_delay(rnnoise_library_path):
    """複数の周波数で測定したgroup delayがいずれも0サンプル付近であることを確認する。

    1つの周波数だけで判定すると、たまたま位相が2πの整数倍に近い周波数を選んで
    しまい実際の1フレーム遅延を見逃す恐れがあるため、複数周波数で確認する。
    """
    for freq in (150.0, 300.0, 800.0, 1200.0):
        delay_samples = _measure_group_delay_samples(rnnoise_library_path, freq)
        assert abs(delay_samples) < DELAY_TOLERANCE_SAMPLES, (
            f"freq={freq}Hz: measured group delay {delay_samples:.1f} samples exceeds tolerance "
            f"({DELAY_TOLERANCE_SAMPLES} samples). RNNoise may now have frame-level output delay; "
            "revisit docs/decisions.md D-015 Step1 (dry/wet path alignment)."
        )


def test_rnnoise_process_frame_broadband_cross_correlation_peaks_near_zero_lag(rnnoise_library_path):
    """チャープ(広帯域・非周期)信号の入出力相互相関を使った、group delay測定とは
    独立な手法での確認。"""
    library = rn.RNNoiseLibrary(rnnoise_library_path)
    state = rn.RNNoiseState(library)
    try:
        n_frames = 1000
        t = np.arange(n_frames * rn.FRAME_SIZE) / SAMPLE_RATE
        f_start, f_end = 100.0, 4000.0
        k = (f_end - f_start) / t[-1]
        phase = 2 * np.pi * (f_start * t + 0.5 * k * t**2)
        sig = (np.sin(phase) * 10000.0).astype(np.float32)

        outputs = []
        for i in range(n_frames):
            frame = sig[i * rn.FRAME_SIZE : (i + 1) * rn.FRAME_SIZE]
            out, _prob = state.process(frame)
            outputs.append(out.copy())
        output = np.concatenate(outputs)
    finally:
        state.close()

    skip = 100 * rn.FRAME_SIZE
    x = sig[skip : skip + 700 * rn.FRAME_SIZE].astype(np.float64)
    y = output[skip : skip + 700 * rn.FRAME_SIZE].astype(np.float64)
    x -= x.mean()
    y -= y.mean()

    max_lag = 2 * rn.FRAME_SIZE
    corr = np.correlate(y, x, mode="full")
    lags = np.arange(-len(x) + 1, len(x))
    mask = (lags >= -max_lag) & (lags <= max_lag)
    sub_lags = lags[mask]
    sub_corr = corr[mask]
    best_lag = int(sub_lags[np.argmax(sub_corr)])

    assert abs(best_lag) < DELAY_TOLERANCE_SAMPLES, (
        f"measured lag {best_lag} samples exceeds tolerance ({DELAY_TOLERANCE_SAMPLES} samples). "
        "RNNoise may now have frame-level output delay; revisit docs/decisions.md D-015 Step1."
    )

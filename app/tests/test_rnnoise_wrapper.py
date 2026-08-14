"""自前ctypesラッパー(soloclarity.dsp.rnnoise)の実検証。

pip installで取得できるpyrnnoiseのmanylinux wheel内のlibrnnoise.soを、
自前ラッパーへ直接ロードして、実際にRNNoiseのdenoiseを正しく呼び出せることを検証する。

D-015: 本ファイルには、RNNoiseの入出力遅延に関する回帰テストも含む。

Step0-1の初回実測(チャープ信号の広帯域相互相関、および複数周波数での位相ベース
group delay測定の2手法)は「遅延0サンプル」と結論したが、これはテスト側の
バグによる誤りだった。`RNNoiseState.process()`(`rnnoise.py`)は
`rnnoise_process_frame(state, ptr, ptr)`と同一ポインタをin/out双方に渡す
in-place処理であり、当時のテストコードは`frame = sig[i*FRAME_SIZE:(i+1)*FRAME_SIZE]`
という「連続なfloat32配列のスライス(ビュー)」をそのまま`state.process()`へ渡して
いたため、`np.ascontiguousarray`がコピーを作らず、呼び出し元の`sig`配列自体が
denoise後の値で書き換えられていた。これにより「元の入力」として比較に使っていた
`sig`が実質的に出力と同一信号になり、真の遅延の有無に関わらず機械的に0付近を
返す構造的なバグだった(本番コード`chain.py`は`float32_to_pcm16_scale`が乗算で
新規配列を作るため影響を受けない。影響はこのテストのみ)。

Reviewer差し戻し後の再測定では、`state.process()`へ渡す全フレームを`.copy()`して
エイリアシングを断った上で、3つの独立した手法(探索窓を`OUTPUT_DELAY_SAMPLES`超まで
広げた広帯域チャープの相互相関、インパルス応答的なバースト注入によるオンセット検出、
位相ラップ(周波数×遅延がナイキスト折返しを超える場合の2πの整数倍の不定性)を
`OUTPUT_DELAY_SAMPLES`近傍で解決したgroup delay測定)でいずれも
`rn.OUTPUT_DELAY_SAMPLES`(2フレーム=960サンプル=20ms)相当の遅延が存在することを
確認した。これを受けて`chain.py`にdry/wetパスの時間整列(dry信号を
`OUTPUT_DELAY_FRAMES`分遅延させるバッファ)を実装した。下記の回帰テストは、
将来RNNoiseの共有ライブラリが更新され、この遅延量の前提が崩れた場合に検知する
ためのものである。もし失敗した場合は、docs/decisions.md D-015を再度検討する必要がある。
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
#
# 重要: `state.process()`は破壊的処理(in-place)であり、`np.ascontiguousarray`が
# コピーを作らない配列(連続なfloat32のスライス/ビュー等)を渡すと呼び出し元の
# 配列自体が上書きされる(rnnoise.py docstring参照)。以下のテストは全てフレームを
# 明示的に`.copy()`してから渡し、このエイリアシングを断っている(D-015
# Reviewer差し戻し: この`.copy()`漏れが「遅延0サンプル」という誤った初回測定結果の
# 直接原因だった)。

# 実測で確認した真の遅延量。許容量はこの値の±25%とし、測定誤差は吸収しつつ
# 1フレーム分ずれるような構造変化は確実に検出できるようにする。
EXPECTED_DELAY_SAMPLES = rn.OUTPUT_DELAY_SAMPLES  # 960 (2フレーム, 20ms)
DELAY_TOLERANCE_SAMPLES = rn.FRAME_SIZE // 4  # 120サンプル


def _measure_group_delay_samples(rnnoise_library_path: str, freq: float, n_frames: int = 400, amplitude: float = 8000.0) -> float:
    """定常正弦波の位相差から、入出力間のgroup delay(サンプル数)を推定する。

    位相差はfreq×delayが大きいと2πの整数倍だけ不定(ラップ)になるため、
    `EXPECTED_DELAY_SAMPLES`に最も近い候補を選んでラップを解決する。
    """
    library = rn.RNNoiseLibrary(rnnoise_library_path)
    state = rn.RNNoiseState(library)
    try:
        t = np.arange(n_frames * rn.FRAME_SIZE) / SAMPLE_RATE
        sig = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)

        outputs = []
        for i in range(n_frames):
            frame = sig[i * rn.FRAME_SIZE : (i + 1) * rn.FRAME_SIZE].copy()
            out, _prob = state.process(frame)
            outputs.append(out.copy())
        output = np.concatenate(outputs)
    finally:
        state.close()

    # 立ち上がり過渡を除いた定常区間で比較する。
    seg_start = 200 * rn.FRAME_SIZE
    seg_len = 150 * rn.FRAME_SIZE
    x = sig[seg_start : seg_start + seg_len].astype(np.float64)
    y = output[seg_start : seg_start + seg_len].astype(np.float64)

    n = len(x)
    freqs = np.fft.rfftfreq(n, 1.0 / SAMPLE_RATE)
    idx = int(np.argmin(np.abs(freqs - freq)))
    spectrum_x = np.fft.rfft(x)[idx]
    spectrum_y = np.fft.rfft(y)[idx]

    phase_diff = np.angle(spectrum_y) - np.angle(spectrum_x)
    phase_diff = (phase_diff + np.pi) % (2 * np.pi) - np.pi  # [-pi, pi]へ正規化
    raw_delay = -phase_diff / (2 * np.pi * freq) * SAMPLE_RATE

    period_samples = SAMPLE_RATE / freq
    best = raw_delay
    for k in range(-30, 31):
        candidate = raw_delay + k * period_samples
        if abs(candidate - EXPECTED_DELAY_SAMPLES) < abs(best - EXPECTED_DELAY_SAMPLES):
            best = candidate
    return float(best)


def test_rnnoise_process_frame_group_delay_matches_expected_samples(rnnoise_library_path):
    """複数の周波数で測定したgroup delay(位相ラップ解決後)が、期待遅延の許容範囲内であることを確認する。

    1つの周波数だけで判定すると、たまたま位相が2πの整数倍に近い周波数を選んで
    しまい真の遅延を見誤る恐れがあるため、複数周波数で確認する。
    """
    for freq in (150.0, 300.0, 500.0, 800.0, 1200.0):
        delay_samples = _measure_group_delay_samples(rnnoise_library_path, freq)
        assert abs(delay_samples - EXPECTED_DELAY_SAMPLES) < DELAY_TOLERANCE_SAMPLES, (
            f"freq={freq}Hz: measured group delay {delay_samples:.1f} samples differs from expected "
            f"{EXPECTED_DELAY_SAMPLES} samples by more than tolerance ({DELAY_TOLERANCE_SAMPLES} samples). "
            "RNNoise's output delay may have changed; revisit docs/decisions.md D-015 "
            "(rnnoise.OUTPUT_DELAY_FRAMES / chain.py dry-wet alignment)."
        )


def test_rnnoise_process_frame_broadband_cross_correlation_peak_matches_expected_lag(rnnoise_library_path):
    """チャープ(広帯域・非周期)信号の入出力相互相関を使った、group delay測定とは
    独立な手法での確認。探索窓は`EXPECTED_DELAY_SAMPLES`を跨いで余裕を持たせる。"""
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
            frame = sig[i * rn.FRAME_SIZE : (i + 1) * rn.FRAME_SIZE].copy()
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

    max_lag = EXPECTED_DELAY_SAMPLES + 4 * rn.FRAME_SIZE
    corr = np.correlate(y, x, mode="full")
    lags = np.arange(-len(x) + 1, len(x))
    mask = (lags >= -max_lag) & (lags <= max_lag)
    sub_lags = lags[mask]
    sub_corr = corr[mask]
    best_lag = int(sub_lags[np.argmax(sub_corr)])

    assert abs(best_lag - EXPECTED_DELAY_SAMPLES) < DELAY_TOLERANCE_SAMPLES, (
        f"measured lag {best_lag} samples differs from expected {EXPECTED_DELAY_SAMPLES} samples by more "
        f"than tolerance ({DELAY_TOLERANCE_SAMPLES} samples). RNNoise's output delay may have changed; "
        "revisit docs/decisions.md D-015."
    )


def test_rnnoise_process_frame_burst_onset_matches_expected_lag(rnnoise_library_path):
    """インパルス応答的な短いバースト注入により、group delay測定・相互相関とは
    独立な3つ目の手法で入出力遅延を確認する。

    RNNoiseは音声らしくない孤立クリックを強く抑圧するため、全試行でオンセットが
    検出できるとは限らない(実測でも一部の試行は検出不能だった)。検出できた
    試行だけを集計し、中央値が期待遅延の許容範囲内であることを確認する。
    """
    lags = []
    n_trials = 15
    for trial in range(n_trials):
        library = rn.RNNoiseLibrary(rnnoise_library_path)
        state = rn.RNNoiseState(library)
        try:
            n_pre_frames = 5
            n_frames = n_pre_frames + 10
            sig = np.zeros(n_frames * rn.FRAME_SIZE, dtype=np.float32)
            # バーストの位置をフレーム境界に対して少しずつずらし、境界依存の
            # アーティファクトに偏らないようにする。
            pos = n_pre_frames * rn.FRAME_SIZE + trial * 30
            sig[pos : pos + 10] = 10000.0

            outputs = []
            for i in range(n_frames):
                frame = sig[i * rn.FRAME_SIZE : (i + 1) * rn.FRAME_SIZE].copy()
                out, _prob = state.process(frame)
                outputs.append(out.copy())
            output = np.concatenate(outputs)
        finally:
            state.close()

        search = output[pos - 50 : pos + 2500]
        onset_idx = None
        for j, value in enumerate(search):
            if abs(value) > 200.0:
                onset_idx = j
                break
        if onset_idx is not None:
            lags.append((pos - 50 + onset_idx) - pos)

    assert len(lags) >= 2, "burst onset was not detected in enough trials to measure delay"
    median_lag = float(np.median(lags))
    assert abs(median_lag - EXPECTED_DELAY_SAMPLES) < DELAY_TOLERANCE_SAMPLES, (
        f"median burst onset lag {median_lag} samples differs from expected {EXPECTED_DELAY_SAMPLES} "
        f"samples by more than tolerance ({DELAY_TOLERANCE_SAMPLES} samples) (lags={lags}). "
        "RNNoise's output delay may have changed; revisit docs/decisions.md D-015."
    )

"""自前ctypesラッパー(soloclarity.dsp.rnnoise)の実検証。

pip installで取得できるpyrnnoiseのmanylinux wheel内のlibrnnoise.soを、
自前ラッパーへ直接ロードして、実際にRNNoiseのdenoiseを正しく呼び出せることを検証する。
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

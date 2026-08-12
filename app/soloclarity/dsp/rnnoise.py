# Apache License 2.0, based on pyrnnoise (https://github.com/pengzhendong/pyrnnoise) rnnoise.py
#
# 本ファイルはpyrnnoiseの低レベルAPI(pyrnnoise/rnnoise.py)と同等のctypes呼び出し規約を
# 自前実装したものであり、pyrnnoiseパッケージ本体(pyrnnoise/pyrnnoise.py等、
# audiolab/av/matplotlib/click/tqdmに依存する重量級モジュール)は一切importしない。
# RNNoise本体(C実装, BSDライセンス, https://gitlab.xiph.org/xiph/rnnoise)の共有ライブラリを
# ctypes経由で直接呼び出すだけの薄いラッパー。

from __future__ import annotations

import ctypes
import os
import platform
from typing import Optional

import numpy as np

FRAME_SIZE = 480  # RNNoiseのネイティブフレームサイズ(48kHz, 10ms)
SAMPLE_RATE = 48000

# int16スケール(おおよそ-32768..32767)に変換して渡すのがRNNoiseのC APIの規約。
# -1.0..1.0の正規化float32との相互変換はこのスケールを介して行う。
PCM16_SCALE = 32768.0


def _default_library_path() -> str:
    """OSごとの共有ライブラリの既定配置場所を返す。

    Windows配布時はbuild_windows.batが `pip install pyrnnoise` から取得した
    rnnoise.dllをこのvendorディレクトリへ配置する(D-001参照)。
    """
    system = platform.system()
    vendor_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
    if system == "Windows":
        name = "rnnoise.dll"
    elif system == "Darwin":
        name = "librnnoise.dylib"
    elif system == "Linux":
        name = "librnnoise.so"
    else:
        raise OSError(f"Unsupported operating system for RNNoise: {system}")
    return os.path.join(vendor_dir, name)


class RNNoiseLibrary:
    """RNNoiseの共有ライブラリをロードし、ctypesの引数/戻り値の型を設定する。

    アプリ実行中は1インスタンスを使い回し、チャンネルごとに`RNNoiseState`を作る。
    """

    def __init__(self, library_path: Optional[str] = None):
        self.path = library_path or _default_library_path()
        if not os.path.exists(self.path):
            raise OSError(f"RNNoise library not found: {self.path}")
        self.lib = ctypes.CDLL(self.path)

        self.lib.rnnoise_create.argtypes = [ctypes.c_void_p]
        self.lib.rnnoise_create.restype = ctypes.c_void_p
        self.lib.rnnoise_destroy.argtypes = [ctypes.c_void_p]
        self.lib.rnnoise_destroy.restype = None
        self.lib.rnnoise_process_frame.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
        ]
        self.lib.rnnoise_process_frame.restype = ctypes.c_float
        self.lib.rnnoise_get_frame_size.restype = ctypes.c_int

        frame_size = self.lib.rnnoise_get_frame_size()
        # 壊れたら失敗する最小限の確認: 本アプリのフレームサイズ設計はRNNoiseの
        # ネイティブフレームサイズ(480)と一致する前提(D-001)のため、ここがずれたら
        # 想定外のRNNoiseバージョンが読み込まれている。
        assert frame_size == FRAME_SIZE, (
            f"RNNoise frame size mismatch: lib reports {frame_size}, expected {FRAME_SIZE}"
        )


class RNNoiseState:
    """1チャンネル分のRNNoise denoise状態。フレームごとに`process`を呼ぶ。"""

    def __init__(self, library: RNNoiseLibrary):
        self._lib = library.lib
        self._state = self._lib.rnnoise_create(None)
        if not self._state:
            raise RuntimeError("rnnoise_create failed")

    def process(self, frame_pcm16_scale: np.ndarray) -> tuple[np.ndarray, float]:
        """int16スケールのfloat32配列(shape=(480,))を処理する。

        Args:
            frame_pcm16_scale: -32768..32767程度の範囲のfloat32配列。
        Returns:
            (denoised_pcm16_scale, speech_probability)
        """
        if self._state is None:
            raise RuntimeError("RNNoiseState is already closed")
        assert frame_pcm16_scale.shape == (FRAME_SIZE,), (
            f"RNNoise requires exactly {FRAME_SIZE} samples, got {frame_pcm16_scale.shape}"
        )
        buf = np.ascontiguousarray(frame_pcm16_scale, dtype=np.float32)
        ptr = buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        speech_prob = self._lib.rnnoise_process_frame(self._state, ptr, ptr)
        return buf, float(speech_prob)

    def close(self) -> None:
        if self._state is not None:
            self._lib.rnnoise_destroy(self._state)
            self._state = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def float32_to_pcm16_scale(frame: np.ndarray) -> np.ndarray:
    """-1.0..1.0の正規化float32を、RNNoise C APIが期待するint16スケールへ変換する。"""
    return (frame * PCM16_SCALE).astype(np.float32)


def pcm16_scale_to_float32(frame: np.ndarray) -> np.ndarray:
    """int16スケールのfloat32を、-1.0..1.0の正規化float32へ変換する。"""
    return (frame / PCM16_SCALE).astype(np.float32)

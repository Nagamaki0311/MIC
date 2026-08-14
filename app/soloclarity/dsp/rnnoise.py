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

# D-015 Reviewer差し戻し(1巡目)対応: rnnoise_process_frameの入出力実測遅延。
# tests/test_rnnoise_wrapper.pyで3つの独立した手法(広帯域チャープ信号の相互相関、
# インパルス応答的なバースト注入、位相ラップを解決したgroup delay測定)により
# 2フレーム(960サンプル, 20ms)であることを確認した(旧測定の「0サンプル」は
# RNNoiseState.process()のin-place破壊によるテスト側のバグだった)。
OUTPUT_DELAY_FRAMES = 2
OUTPUT_DELAY_SAMPLES = OUTPUT_DELAY_FRAMES * FRAME_SIZE

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

        破壊的処理(in-place)である点に注意: `rnnoise_process_frame`へ同一ポインタを
        in/out双方として渡すため、引数がC言語連続配列(`np.ascontiguousarray`が
        コピーを作らない場合、すなわち既にfloat32でメモリ連続な配列やそのビュー)
        であれば、**呼び出し元が保持している配列自体もdenoise後の値で上書きされる**。
        呼び出し元の元データを保持したい場合は、渡す前に`frame_pcm16_scale.copy()`
        すること(D-015 Reviewer差し戻し: この仕様を知らずに配列スライスをそのまま
        渡した結果、遅延測定テストの「元の入力」が実質的に出力と同一信号になり
        誤った測定結果を招いたことがある)。`chain.py`は`float32_to_pcm16_scale`が
        乗算により毎回新規配列を確保するため、この問題の影響を受けない。

        戻り値の`denoised`は入力に対しOUTPUT_DELAY_FRAMES(2フレーム, 20ms)分
        遅れて出力される(実測: tests/test_rnnoise_wrapper.py参照)。

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

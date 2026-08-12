"""入出力ストリーム管理。コールバックでVoiceChainを呼ぶ。

実デバイスへのstart/stopはこのLinux開発環境では検証できない
(WINDOWS_VERIFICATION_CHECKLIST.md参照)。DSPロジック自体はVoiceChain側で
テスト済み(app/tests/test_chain.py)であり、本モジュールはsounddeviceの
ストリームAPIへ薄く配線するだけの役割にとどめる。
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from soloclarity.dsp.chain import FRAME_SIZE, SAMPLE_RATE, VoiceChain
from soloclarity.dsp.meter import LevelMeter

# (in_rms_dbfs, in_peak_dbfs, out_rms_dbfs, out_peak_dbfs)
MeterCallback = Callable[[float, float, float, float], None]
# PortAudioのコールバックスレッドで発生したエラーメッセージを1つ受け取る。
ErrorCallback = Callable[[str], None]


class AudioEngine:
    """マイク入力 -> VoiceChain -> 仮想マイク出力のリアルタイムストリームを管理する。"""

    def __init__(
        self,
        chain: VoiceChain,
        input_device: Optional[int] = None,
        output_device: Optional[int] = None,
        on_meter_update: Optional[MeterCallback] = None,
        on_error: Optional[ErrorCallback] = None,
    ):
        self.chain = chain
        self.input_device = input_device
        self.output_device = output_device
        self.on_meter_update = on_meter_update
        self.on_error = on_error
        self.bypass = False
        self._input_meter = LevelMeter()
        self._output_meter = LevelMeter()
        self._stream: Optional[sd.Stream] = None

    def _callback(self, indata, outdata, frames, time_info, status) -> None:
        del time_info  # 未使用
        if status:
            # under/overflow等のPortAudio警告。処理は継続する(音切れより継続を優先)。
            pass
        frame = np.ascontiguousarray(indata[:, 0], dtype=np.float32)
        in_rms, in_peak = self._input_meter.update(frame)

        if self.bypass:
            processed = frame
        else:
            try:
                processed, _speech_prob = self.chain.process(frame)
            except Exception as exc:
                # チェーン内部の異常(不正なadvanced_overrides由来の異常値等)で
                # コールバックスレッドが例外で落ちると音声処理が静かに止まって
                # しまう。バイパス(無加工の入力をそのまま出力)にフォールバックし、
                # GUI側へエラーを伝える。
                processed = frame
                if self.on_error is not None:
                    self.on_error(str(exc))

        out_rms, out_peak = self._output_meter.update(processed)
        if self.on_meter_update is not None:
            self.on_meter_update(in_rms, in_peak, out_rms, out_peak)
        outdata[:, 0] = processed

    def start(self) -> None:
        if self._stream is not None:
            return
        stream = sd.Stream(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SIZE,
            dtype="float32",
            channels=1,
            device=(self.input_device, self.output_device),
            callback=self._callback,
        )
        try:
            stream.start()
        except Exception:
            # Pa_OpenStream(sd.Stream(...))は成功したがPa_StartStream(.start())が
            # 失敗したケース。sounddevice.Streamに__del__は無くGCでも解放されない
            # ため、ここでcloseしないとPaStreamハンドルがリークする(Reviewer指摘2)。
            # self._streamへは代入前なので、失敗時に参照が残らないようにする。
            stream.close()
            raise
        self._stream = stream

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def is_running(self) -> bool:
        return self._stream is not None


def record_and_process_preview(
    chain: VoiceChain, input_device: Optional[int], duration_seconds: float = 3.0
) -> np.ndarray:
    """マイクから数秒録音し、chainで処理した波形を返す(テストボタン用)。

    再生は`play_preview`側で行う。DiscordやGUIを介さずに処理後の音を
    確認できるようにするための機能(仕様書のテストボタン要件)。
    """
    num_frames = int(duration_seconds * SAMPLE_RATE / FRAME_SIZE)
    total_samples = num_frames * FRAME_SIZE
    recorded = sd.rec(
        total_samples, samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=input_device
    )
    sd.wait()
    recorded_mono = recorded[:, 0]

    output = np.zeros_like(recorded_mono)
    for i in range(num_frames):
        start = i * FRAME_SIZE
        end = start + FRAME_SIZE
        processed, _speech_prob = chain.process(recorded_mono[start:end])
        output[start:end] = processed
    return output


def play_preview(audio: np.ndarray, output_device: Optional[int]) -> None:
    sd.play(audio, samplerate=SAMPLE_RATE, device=output_device)
    sd.wait()

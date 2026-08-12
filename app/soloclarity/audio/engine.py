"""入出力ストリーム管理。コールバックでVoiceChainを呼ぶ。

実デバイスへのstart/stopはこのLinux開発環境では検証できない
(WINDOWS_VERIFICATION_CHECKLIST.md参照)。DSPロジック自体はVoiceChain側で
テスト済み(app/tests/test_chain.py)であり、本モジュールはsounddeviceの
ストリームAPIへ薄く配線するだけの役割にとどめる。

## InputStream/OutputStreamの2本構成について(D-009)

マイク(SoloCast等)と仮想マイク(CABLE Input等)という別デバイスを単一の
双方向sd.Streamで結合すると、WASAPI上でpaBadIODeviceCombination
(PaErrorCode -9993)になることが実機で確認された(異なるデバイス・
クロックドメインを1本のフルデュプレックスストリームへ結合すること自体が
PortAudio/WASAPIの一般的な制約)。そのため入力(sd.InputStream)と
出力(sd.OutputStream)を独立したストリームとして開き、小さな有界の
リングバッファ(ジッタバッファ)で橋渡しする。両ストリームは別々の
コールバックスレッドから駆動されるため、リングバッファはロックで保護する
(クリティカルセクションはdeque.append/popleftのO(1)操作のみであり、
PortAudioのリアルタイム制約(コールバックは短時間で返る必要がある)を
損なわない。バッファが満杯/空の場合もブロッキング待機は行わない)。
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from soloclarity.dsp.chain import FRAME_SIZE, SAMPLE_RATE, VoiceChain
from soloclarity.dsp.meter import LevelMeter

# (in_rms_dbfs, in_peak_dbfs, out_rms_dbfs, out_peak_dbfs)
MeterCallback = Callable[[float, float, float, float], None]
# PortAudioのコールバックスレッドで発生したエラーメッセージを1つ受け取る。
ErrorCallback = Callable[[str], None]

# ジッタバッファのフレーム数。1フレーム=10ms(FRAME_SIZE=480, 48kHz)なので
# 4フレーム=40ms。入出力ストリームのクロックドリフト・スケジューリング揺れを
# 吸収しつつ体感できる遅延を増やしすぎない範囲として、D-009で定めた目安
# (2〜6フレーム=20〜60ms)の中間値を採用した。
JITTER_BUFFER_FRAMES = 4


class _FrameRingBuffer:
    """入力側コールバックスレッドと出力側コールバックスレッドの間でフレームを
    橋渡しする有界リングバッファ。

    push()は満杯時に最も古いフレームを破棄する(non-blocking、例外を出さない)。
    pop()は空の場合Noneを返す(non-blocking、例外を出さない)。
    """

    def __init__(self, maxlen: int):
        self._frames: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frames.append(frame)  # maxlen超過時はdequeが自動で最古を破棄する

    def pop(self) -> Optional[np.ndarray]:
        with self._lock:
            if not self._frames:
                return None
            return self._frames.popleft()

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)


class AudioEngine:
    """マイク入力 -> VoiceChain -> 仮想マイク出力のリアルタイムストリームを管理する。

    入力(SoloCast等)と出力(CABLE Input等)は別デバイスであり得るため、独立した
    sd.InputStream/sd.OutputStreamをリングバッファで橋渡しする構成にしている
    (D-009)。
    """

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
        self._buffer = _FrameRingBuffer(JITTER_BUFFER_FRAMES)
        # 出力側コールバックが直近の入力メーター値を参照するための共有状態。
        # タプルへの再代入はCPythonでは単一のSTORE_ATTR/LOAD_ATTRで完結し、
        # 読み取り側が新旧混在の値(部分更新)を観測することはないため、
        # 追加のロックは設けていない。
        self._last_input_levels: tuple[float, float] = (
            self._input_meter.floor_db,
            self._input_meter.floor_db,
        )
        self._input_stream: Optional[sd.InputStream] = None
        self._output_stream: Optional[sd.OutputStream] = None

    def _input_callback(self, indata, frames, time_info, status) -> None:
        del frames, time_info  # 未使用
        if status:
            # under/overflow等のPortAudio警告。処理は継続する(音切れより継続を優先)。
            pass
        frame = np.ascontiguousarray(indata[:, 0], dtype=np.float32)
        in_rms, in_peak = self._input_meter.update(frame)
        self._last_input_levels = (in_rms, in_peak)

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

        self._buffer.push(processed)

    def _output_callback(self, outdata, frames, time_info, status) -> None:
        del time_info  # 未使用
        if status:
            # アンダーラン等のPortAudio警告。無音で埋めて継続する。
            pass
        frame = self._buffer.pop()
        if frame is None:
            # ジッタバッファが空(起動直後・クロックドリフト等による一時的な
            # アンダーラン)。ノイズや未初期化メモリを出力しないよう無音を書く。
            frame = np.zeros(frames, dtype=np.float32)

        # 出力メーターは実際に書き出す値(アンダーラン時の無音を含む)を測る。
        # 入力側で測ると、アンダーランでフレームが欠落しても「処理はできて
        # いた」ことになってしまい、実際にDiscord側へ届く音量と乖離するため、
        # 出力側で(実際に書き出す値を)測る設計にした(D-009追記参照)。
        out_rms, out_peak = self._output_meter.update(frame)
        if self.on_meter_update is not None:
            in_rms, in_peak = self._last_input_levels
            self.on_meter_update(in_rms, in_peak, out_rms, out_peak)
        outdata[:, 0] = frame

    @staticmethod
    def _open_and_start(factory, device, callback):
        stream = factory(
            samplerate=SAMPLE_RATE,
            blocksize=FRAME_SIZE,
            dtype="float32",
            channels=1,
            device=device,
            callback=callback,
        )
        try:
            stream.start()
        except Exception:
            # Pa_OpenStream(factory(...))は成功したがPa_StartStream(.start())が
            # 失敗したケース。sounddeviceのストリームクラスに__del__は無くGCでも
            # 解放されないため、ここでcloseしないとPaStreamハンドルがリークする
            # (D-006 Reviewer指摘2と同型のパターンを2ストリームへ適用)。
            stream.close()
            raise
        return stream

    def start(self) -> None:
        if self._input_stream is not None or self._output_stream is not None:
            return
        input_stream = self._open_and_start(sd.InputStream, self.input_device, self._input_callback)
        try:
            output_stream = self._open_and_start(
                sd.OutputStream, self.output_device, self._output_callback
            )
        except Exception:
            # 入力ストリームは開始済みのため、出力側の失敗時はここでstop/closeして
            # リークを防いでから例外を再送出する(D-009決定)。
            input_stream.stop()
            input_stream.close()
            raise
        self._input_stream = input_stream
        self._output_stream = output_stream

    def stop(self) -> None:
        if self._input_stream is not None:
            self._input_stream.stop()
            self._input_stream.close()
            self._input_stream = None
        if self._output_stream is not None:
            self._output_stream.stop()
            self._output_stream.close()
            self._output_stream = None

    def is_running(self) -> bool:
        return self._input_stream is not None and self._output_stream is not None


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

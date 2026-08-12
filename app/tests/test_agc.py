from __future__ import annotations

import numpy as np

from soloclarity.dsp.agc import AutomaticGainControl
from soloclarity.dsp.meter import linear_to_dbfs, rms


def _make_tone_frame(amplitude: float, frame_index: int, freq: float = 150.0, sr: int = 48000):
    t = (np.arange(480) + frame_index * 480) / sr
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_agc_raises_quiet_signal_toward_target():
    """振幅の小さい合成音(peak -30dBFS相当)に対し、AGC適用後のRMSがtargetへ近づく方向に持ち上がる。"""
    # -30dBFS peak相当の振幅
    amplitude = 10 ** (-30.0 / 20.0)
    agc = AutomaticGainControl(target_dbfs=-17.0, max_gain_db=10.0, attack_seconds=0.3, release_seconds=1.0)

    n_frames = 500  # 5秒分, 発話ありと仮定してゲイン更新を有効にする
    in_rms_list = []
    out_rms_list = []
    for i in range(n_frames):
        frame = _make_tone_frame(amplitude, i)
        out = agc.process(frame, speech_prob=1.0)
        in_rms_list.append(rms(frame))
        out_rms_list.append(rms(out))

    input_dbfs = linear_to_dbfs(np.mean(in_rms_list[-50:]))
    output_dbfs_start = linear_to_dbfs(out_rms_list[0])
    output_dbfs_end = linear_to_dbfs(np.mean(out_rms_list[-50:]))

    target_dbfs = -17.0
    assert input_dbfs < target_dbfs  # 前提: 入力は確かに小さい
    # 出力は入力よりtargetに近づいている(持ち上がる方向)
    assert output_dbfs_end > input_dbfs
    assert abs(output_dbfs_end - target_dbfs) < abs(input_dbfs - target_dbfs)
    assert output_dbfs_end > output_dbfs_start  # 時間とともに持ち上がっている


def test_agc_gain_updates_freeze_when_speech_probability_is_low():
    agc = AutomaticGainControl(target_dbfs=-17.0, max_gain_db=10.0, attack_seconds=0.3, release_seconds=1.0)
    amplitude = 10 ** (-30.0 / 20.0)

    # 発話確率が高い状態で数十フレーム流し、ゲインを動かす
    for i in range(50):
        agc.process(_make_tone_frame(amplitude, i), speech_prob=1.0)
    gain_after_speech = agc._gain

    # 発話確率が低い状態(無音扱い)では、振幅が変化してもゲインは更新されない
    for i in range(50, 100):
        agc.process(_make_tone_frame(amplitude * 5, i), speech_prob=0.0)
    assert agc._gain == gain_after_speech


def test_agc_does_not_exceed_max_gain():
    very_quiet_amplitude = 10 ** (-60.0 / 20.0)
    max_gain_db = 6.0
    agc = AutomaticGainControl(
        target_dbfs=-17.0, max_gain_db=max_gain_db, attack_seconds=0.1, release_seconds=0.5
    )
    for i in range(1000):
        agc.process(_make_tone_frame(very_quiet_amplitude, i), speech_prob=1.0)
    max_gain_linear = 10 ** (max_gain_db / 20.0)
    assert agc._gain <= max_gain_linear + 1e-9

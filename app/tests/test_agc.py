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
        out = agc.process(frame, speech_active=True)
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


def test_agc_gain_updates_freeze_when_speech_is_inactive():
    agc = AutomaticGainControl(target_dbfs=-17.0, max_gain_db=10.0, attack_seconds=0.3, release_seconds=1.0)
    amplitude = 10 ** (-30.0 / 20.0)

    # 発話アクティブな状態で数十フレーム流し、ゲインを動かす
    for i in range(50):
        agc.process(_make_tone_frame(amplitude, i), speech_active=True)
    gain_after_speech = agc._gain

    # 発話が非アクティブな間は、振幅が変化してもゲインは更新されない
    for i in range(50, 100):
        agc.process(_make_tone_frame(amplitude * 5, i), speech_active=False)
    assert agc._gain == gain_after_speech


def test_agc_does_not_exceed_max_gain():
    very_quiet_amplitude = 10 ** (-60.0 / 20.0)
    max_gain_db = 6.0
    agc = AutomaticGainControl(
        target_dbfs=-17.0, max_gain_db=max_gain_db, attack_seconds=0.1, release_seconds=0.5
    )
    for i in range(1000):
        agc.process(_make_tone_frame(very_quiet_amplitude, i), speech_active=True)
    max_gain_linear = 10 ** (max_gain_db / 20.0)
    assert agc._gain <= max_gain_linear + 1e-9


def test_set_params_updates_coefficients_without_resetting_gain_state():
    """D-015: 詳細設定スライダー操作でAGCを作り直さず係数だけ更新すると、
    ゲイン・RMSエンベロープが保持される(声が一瞬消えるバグの修正)。"""
    agc = AutomaticGainControl(target_dbfs=-17.0, max_gain_db=10.0, attack_seconds=0.3, release_seconds=1.0)
    amplitude = 10 ** (-30.0 / 20.0)
    for i in range(50):
        agc.process(_make_tone_frame(amplitude, i), speech_active=True)
    gain_before = agc._gain
    envelope_before = agc._rms_envelope

    agc.set_params(target_dbfs=-20.0, max_gain_db=12.0, attack_seconds=0.4, release_seconds=1.5)

    assert agc._gain == gain_before
    assert agc._rms_envelope == envelope_before
    assert agc.target_dbfs == -20.0
    assert agc.max_gain_db == 12.0


def test_gain_is_applied_as_a_within_frame_ramp_not_a_step():
    """D-015: フレーム境界でのゲイン不連続(クリック)を避けるため、フレーム内で
    前回値から今回値へ線形ランプする。"""
    agc = AutomaticGainControl(target_dbfs=-6.0, max_gain_db=20.0, attack_seconds=0.01, release_seconds=0.01)
    # 最初のフレームで大振幅を入れ、ゲインが急に動く状況を作る。
    frame = _make_tone_frame(10 ** (-40.0 / 20.0), 0)
    out = agc.process(frame, speech_active=True)
    # フレーム内で一定倍率(ステップ適用)なら frame*gain == out が成り立ってしまう。
    # ランプが効いていれば、先頭と末尾で実効ゲインが異なるはず。
    nonzero = np.abs(frame) > 1e-6
    ratios = out[nonzero] / frame[nonzero]
    assert not np.allclose(ratios, ratios[0], atol=1e-6), "gain should ramp within the frame, not step"


def test_set_params_clamps_existing_gain_to_new_max_when_speech_is_inactive():
    """D-015 Reviewer差し戻し(1巡目): プリセット切替でmax_gain_dbがより小さい値へ
    変わった直後、発話が非アクティブ(凍結中)でも、旧プリセットで収束した(より
    大きい)ゲインが新プリセットの範囲へ即座にクランプされることを確認する。
    """
    agc = AutomaticGainControl(target_dbfs=-16.0, max_gain_db=12.0, attack_seconds=0.1, release_seconds=0.5)
    very_quiet_amplitude = 10 ** (-60.0 / 20.0)
    for i in range(200):
        agc.process(_make_tone_frame(very_quiet_amplitude, i), speech_active=True)
    old_max_gain_linear = 10 ** (12.0 / 20.0)
    assert agc._gain > 10 ** (6.0 / 20.0)  # 前提: 旧プリセットの上限(12dB)近くまで収束している
    assert agc._gain <= old_max_gain_linear + 1e-9

    # natural相当(max_gain_db=6.0)へ切り替え、発話は非アクティブ(凍結中)のまま。
    agc.set_params(target_dbfs=-20.0, max_gain_db=6.0, attack_seconds=0.4, release_seconds=1.5)
    new_max_gain_linear = 10 ** (6.0 / 20.0)
    assert agc._gain <= new_max_gain_linear + 1e-9

    # 凍結中でも(speech_active=False)クランプ後のゲインが維持され、範囲を超えない。
    agc.process(_make_tone_frame(very_quiet_amplitude, 200), speech_active=False)
    assert agc._gain <= new_max_gain_linear + 1e-9


class TestAgcConvergenceSpeed:
    """D-015: attack/releaseを2.0s/4.0sから0.4s/1.5sへ短縮し、数秒の発話内で
    target±3dBへ収束できることを実測で確認する(旧時定数では収束しなかったケース)。
    """

    def _seconds_to_converge(self, attack_s: float, release_s: float, input_dbfs: float, target_dbfs: float = -17.0) -> float | None:
        amplitude = 10 ** (input_dbfs / 20.0)
        agc = AutomaticGainControl(target_dbfs=target_dbfs, max_gain_db=12.0, attack_seconds=attack_s, release_seconds=release_s)
        for i in range(1000):
            frame = _make_tone_frame(amplitude, i)
            out = agc.process(frame, speech_active=True)
            out_dbfs = linear_to_dbfs(rms(out))
            if abs(out_dbfs - target_dbfs) <= 3.0:
                return i * 480 / 48000
        return None

    def test_new_time_constants_converge_within_three_seconds(self):
        converge_s = self._seconds_to_converge(attack_s=0.4, release_s=1.5, input_dbfs=-25.0)
        assert converge_s is not None
        assert converge_s <= 3.0

    def test_new_time_constants_are_faster_than_old_defaults(self):
        old_converge_s = self._seconds_to_converge(attack_s=2.0, release_s=4.0, input_dbfs=-25.0)
        new_converge_s = self._seconds_to_converge(attack_s=0.4, release_s=1.5, input_dbfs=-25.0)
        assert old_converge_s is not None
        assert new_converge_s is not None
        assert new_converge_s < old_converge_s

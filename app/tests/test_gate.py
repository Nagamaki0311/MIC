from __future__ import annotations

import numpy as np

from soloclarity.dsp.gate import SpeechProbabilityGate


def test_gate_opens_for_high_speech_probability():
    gate = SpeechProbabilityGate(threshold=0.3, release_ms=200.0, attack_ms=5.0)
    frame = np.ones(480, dtype=np.float32) * 0.5
    out = frame
    for _ in range(20):  # attackが十分収束するまで回す
        out = gate.apply(frame, speech_prob=0.9)
    assert np.allclose(out, frame, atol=1e-3)


def test_gate_attenuates_low_speech_probability_after_release():
    gate = SpeechProbabilityGate(threshold=0.3, release_ms=100.0, attack_ms=5.0)
    frame = np.ones(480, dtype=np.float32) * 0.5

    # まず発話ありでゲートを開く
    for _ in range(20):
        gate.apply(frame, speech_prob=0.9)

    # 発話確率が閾値未満になった後、十分な時間(release_msの何倍も)が経てば閉じる
    out = frame
    for _ in range(100):  # 100frame * 10ms = 1000ms >> release 100ms
        out = gate.apply(frame, speech_prob=0.0)
    assert np.max(np.abs(out)) < 0.01 * np.max(np.abs(frame))


def test_gate_white_noise_is_attenuated_when_probability_stays_low():
    """ホワイトノイズのみ(無音相当、発話確率が低いはず)に対し、ゲートが減衰させる。"""
    rng = np.random.default_rng(0)
    gate = SpeechProbabilityGate(threshold=0.3, release_ms=150.0, attack_ms=5.0)
    total_in_energy = 0.0
    total_out_energy = 0.0
    for _ in range(200):
        noise_frame = (rng.normal(0.0, 0.02, 480)).astype(np.float32)
        low_speech_prob = 0.05  # ホワイトノイズはRNNoise上、発話確率が低く出るはず
        out = gate.apply(noise_frame, low_speech_prob)
        total_in_energy += float(np.sum(noise_frame**2))
        total_out_energy += float(np.sum(out**2))
    assert total_out_energy < total_in_energy * 0.1


def test_release_time_roughly_matches_configured_ms():
    """release_msが長いほど、閉じきるまでのフレーム数が増えることを確認する。"""
    frame = np.ones(480, dtype=np.float32)

    def frames_to_close(release_ms: float) -> int:
        gate = SpeechProbabilityGate(threshold=0.3, release_ms=release_ms, attack_ms=5.0)
        for _ in range(20):
            gate.apply(frame, speech_prob=0.9)
        count = 0
        out = frame
        while np.max(np.abs(out)) > 0.01 and count < 1000:
            out = gate.apply(frame, speech_prob=0.0)
            count += 1
        return count

    short = frames_to_close(120.0)
    long = frames_to_close(300.0)
    assert long > short

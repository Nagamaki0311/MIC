from __future__ import annotations

import numpy as np
import pytest

from soloclarity import presets
from soloclarity.dsp.gate import (
    GATE_FLOOR_DB,
    SpeechActivityTracker,
    SpeechProbabilityGate,
)


def test_gate_opens_for_high_speech_probability():
    gate = SpeechProbabilityGate(threshold=0.3, release_ms=200.0, attack_ms=5.0)
    frame = np.ones(480, dtype=np.float32) * 0.5
    out = frame
    for _ in range(20):  # attackが十分収束するまで回す
        out = gate.apply(frame, speech_active=True)
    assert np.allclose(out, frame, atol=1e-3)


def test_gate_attenuates_low_speech_probability_after_release():
    gate = SpeechProbabilityGate(threshold=0.3, release_ms=100.0, attack_ms=5.0)
    frame = np.ones(480, dtype=np.float32) * 0.5

    # まず発話ありでゲートを開く
    for _ in range(20):
        gate.apply(frame, speech_active=True)

    # 発話が非アクティブになった後、十分な時間(release_msの何倍も)が経てば
    # フロア付近まで減衰する(完全な無音にはならない)。
    out = frame
    for _ in range(100):  # 100frame * 10ms = 1000ms >> release 100ms
        out = gate.apply(frame, speech_active=False)
    floor_linear = 10.0 ** (GATE_FLOOR_DB / 20.0)
    assert np.max(np.abs(out)) == pytest.approx(floor_linear * np.max(np.abs(frame)), rel=0.05)


def test_gate_never_reaches_full_silence_even_with_long_non_speech():
    """完全ミュート(0.0)ではなくGATE_FLOOR_DBへダッキングする(D-015)。"""
    gate = SpeechProbabilityGate(threshold=0.3, release_ms=50.0, attack_ms=5.0)
    frame = np.ones(480, dtype=np.float32) * 0.5
    out = frame
    for _ in range(500):
        out = gate.apply(frame, speech_active=False)
    assert np.max(np.abs(out)) > 0.0


def test_gate_white_noise_is_attenuated_when_probability_stays_low():
    """ホワイトノイズのみ(無音相当、発話確率が低いはず)に対し、ゲートが減衰させる。"""
    rng = np.random.default_rng(0)
    gate = SpeechProbabilityGate(threshold=0.3, release_ms=150.0, attack_ms=5.0)
    total_in_energy = 0.0
    total_out_energy = 0.0
    for _ in range(200):
        noise_frame = (rng.normal(0.0, 0.02, 480)).astype(np.float32)
        out = gate.apply(noise_frame, speech_active=False)
        total_in_energy += float(np.sum(noise_frame**2))
        total_out_energy += float(np.sum(out**2))
    assert total_out_energy < total_in_energy * 0.1


def test_release_time_roughly_matches_configured_ms():
    """release_msが長いほど、フロアへ落ち着くまでのフレーム数が増えることを確認する。"""
    frame = np.ones(480, dtype=np.float32)
    floor_linear = 10.0 ** (GATE_FLOOR_DB / 20.0)

    def frames_to_settle(release_ms: float) -> int:
        gate = SpeechProbabilityGate(threshold=0.3, release_ms=release_ms, attack_ms=5.0)
        for _ in range(20):
            gate.apply(frame, speech_active=True)
        count = 0
        out = frame
        target = floor_linear * 1.01  # フロアへほぼ収束したとみなす閾値
        while np.max(np.abs(out)) > target and count < 2000:
            out = gate.apply(frame, speech_active=False)
            count += 1
        return count

    short = frames_to_settle(120.0)
    long = frames_to_settle(300.0)
    assert long > short


class TestGateAgainstNoiseStagePresets:
    """明瞭度ではなく実際のノイズ除去段階(弱/標準/強)のgate_threshold/gate_release_msを
    使い、語尾・小さい声を不必要に削っていないかをattack/releaseの実測値で確認する。
    """

    @pytest.mark.parametrize("level", presets.NOISE_LEVELS)
    def test_soft_but_sustained_speech_opens_within_a_few_frames(self, level):
        """立ち上がりが遅い小さい声を想定し、ゲートが不必要に頭を削らない(すぐ開く)ことを確認する。"""
        stage = presets.NOISE_STAGES[level]
        gate = SpeechProbabilityGate(threshold=stage.gate_threshold, release_ms=stage.gate_release_ms)
        frame = np.ones(480, dtype=np.float32) * 0.3

        opened_at = None
        out = frame
        for i in range(50):
            out = gate.apply(frame, speech_active=True)
            if opened_at is None and np.max(np.abs(out)) > 0.95 * np.max(np.abs(frame)):
                opened_at = i

        assert opened_at is not None, f"{level}: gate never fully opened for sustained soft speech"
        # attack_ms=5ms(0.5フレーム)は十分小さいため、数フレーム以内に開くはず。
        assert opened_at <= 5, f"{level}: gate took {opened_at} frames to open (word onset would be clipped)"

    @pytest.mark.parametrize("level", presets.NOISE_LEVELS)
    def test_word_tail_fades_gradually_instead_of_cutting_abruptly(self, level):
        """語尾で発話が非アクティブになった直後の1フレームで、いきなり無音にならないこと
        (release_msに応じて滑らかに減衰する)。"""
        stage = presets.NOISE_STAGES[level]
        gate = SpeechProbabilityGate(threshold=stage.gate_threshold, release_ms=stage.gate_release_ms)
        frame = np.ones(480, dtype=np.float32) * 0.3
        for _ in range(30):
            gate.apply(frame, speech_active=True)

        out = gate.apply(frame, speech_active=False)
        assert np.max(np.abs(out)) > 0.01, (
            f"{level}: gate cuts to near-silence within a single 10ms frame after the tail "
            "of a word (release_ms is not being honored)"
        )


class TestSpeechActivityTracker:
    """D-015: ヒステリシス(開く閾値/閉じる閾値=開く閾値×0.5)とhangover(既定200ms)で
    発話確率のちらつきに対して発話状態を安定させる。
    """

    def test_opens_when_probability_reaches_open_threshold(self):
        tracker = SpeechActivityTracker(open_threshold=0.25)
        assert tracker.update(0.1) is False
        assert tracker.update(0.25) is True
        assert tracker.update(0.9) is True

    def test_stays_active_in_hysteresis_band_between_close_and_open_threshold(self):
        """開く閾値の半分(閉じる閾値)〜開く閾値の間は、いったん開いたら閉じない。"""
        tracker = SpeechActivityTracker(open_threshold=0.4, hangover_ms=0.0)
        assert tracker.update(0.4) is True
        # 0.4*0.5=0.2(閉じる閾値)以上なので、hangoverが無くても閉じないはず。
        for _ in range(10):
            assert tracker.update(0.25) is True

    def test_hangover_keeps_active_briefly_after_dropping_below_close_threshold(self):
        tracker = SpeechActivityTracker(open_threshold=0.4, hangover_ms=200.0)  # 20フレーム相当
        tracker.update(0.9)
        assert tracker._active is True

        # 閉じる閾値(0.2)を割った直後はまだアクティブ(hangover消化中)。
        still_active_frames = 0
        for _ in range(19):
            if tracker.update(0.0):
                still_active_frames += 1
        assert still_active_frames == 19, "hangover中は非アクティブへ切り替わらないはず"

        # hangoverを使い切ると非アクティブになる。
        for _ in range(5):
            active = tracker.update(0.0)
        assert active is False

    def test_flickering_probability_around_threshold_does_not_rapidly_toggle(self):
        """発話確率が開く閾値の近くで揺れても(ヒステリシス帯に収まる限り)、
        頻繁にopen/closeを繰り返さないことを確認する(D-015の「プツプツ途切れる」対策)。
        """
        tracker = SpeechActivityTracker(open_threshold=0.3, hangover_ms=200.0)
        tracker.update(0.9)  # 一旦開く
        toggled_to_inactive = 0
        prev_active = True
        rng_values = [0.28, 0.22, 0.29, 0.24, 0.27, 0.23, 0.26] * 5  # 閉じる閾値0.15より高い範囲で揺れる
        for v in rng_values:
            active = tracker.update(v)
            if prev_active and not active:
                toggled_to_inactive += 1
            prev_active = active
        assert toggled_to_inactive == 0

    def test_set_params_updates_thresholds_without_resetting_active_state(self):
        tracker = SpeechActivityTracker(open_threshold=0.3)
        tracker.update(0.9)
        assert tracker._active is True
        tracker.set_params(open_threshold=0.5)
        assert tracker._active is True  # set_params自体は状態をリセットしない
        assert tracker.open_threshold == 0.5
        assert tracker.close_threshold == 0.25

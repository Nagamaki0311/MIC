"""VoiceChainの長時間動作安定性(メモリリーク・処理時間劣化)を検証するソークテスト。

`python -m tests.soak_chain`で実行し、RSS(常駐メモリ)と処理時間の推移を表示できる。
pytest経由でも実行できる(`pytest tests/soak_chain.py`)。

音声らしいsin波+ノイズ混合区間・無音区間・ノイズのみ区間を周期的に混在させた
合成信号を10万フレーム(48kHz, 480サンプル/フレーム=1000秒相当)流し続け、
RSSが無制限に増加し続けていないか、フレームあたりの処理時間が時間経過で
悪化していないかを確認する。

RSS測定にはPOSIXの`resource`モジュールを使うため、Windows(このプロジェクトの
配布対象)では`resource`が存在せず実行できない。Windows実機での常駐メモリ実測は
WINDOWS_VERIFICATION_CHECKLIST.mdでユーザーに確認してもらう(このモジュールは
開発環境(Linux)での自動ソークテスト用)。
"""

from __future__ import annotations

import time

import numpy as np

from soloclarity.dsp.chain import FRAME_SIZE, SAMPLE_RATE, VoiceChain
from tests._rnnoise_test_lib import find_rnnoise_test_library_path

try:
    import resource
except ImportError:  # Windows: このソークテストはスキップされる
    resource = None

N_FRAMES = 100_000  # 480サンプル/フレーム, 48kHzで1000秒相当
RSS_SAMPLE_INTERVAL = 10_000
TIMING_BATCH_SIZE = 10_000
# 序盤の一時的なアロケーション(numpy/pedalboardの初期化等)を除いた後の
# RSS成長率がこの倍率未満に収まっていること(無制限な増加=リークの兆候ではないこと)。
RSS_GROWTH_RATIO_THRESHOLD = 1.3
# 先頭1万フレームと末尾1万フレームの平均処理時間の比がこの倍率未満であること。
TIMING_SLOWDOWN_RATIO_THRESHOLD = 1.5


def _make_frame(rng: np.random.Generator, i: int) -> np.ndarray:
    """音声らしいsin波+ノイズ混合/無音/ノイズのみを周期的に切り替える合成信号。"""
    t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / SAMPLE_RATE
    phase = i % 300  # 3秒周期(発話1秒 -> 無音1秒 -> ノイズのみ1秒)
    if phase < 100:
        tone = 0.15 * np.sin(2 * np.pi * 180 * t)
        noise = rng.normal(0.0, 0.01, FRAME_SIZE)
        frame = tone + noise
    elif phase < 200:
        frame = np.zeros(FRAME_SIZE)
    else:
        frame = rng.normal(0.0, 0.05, FRAME_SIZE)
    return frame.astype(np.float32)


def run_soak_test(n_frames: int = N_FRAMES) -> dict:
    assert resource is not None, "soak test requires the POSIX resource module"

    library_path = find_rnnoise_test_library_path()
    chain = VoiceChain("discord_call", rnnoise_library_path=library_path)
    rng = np.random.default_rng(7)

    rss_samples_kb: list[int] = []
    first_batch_times: list[float] = []
    last_batch_times: list[float] = []
    last_batch_start = n_frames - TIMING_BATCH_SIZE

    for i in range(n_frames):
        frame = _make_frame(rng, i)
        start = time.perf_counter()
        chain.process(frame)
        elapsed = time.perf_counter() - start

        if i < TIMING_BATCH_SIZE:
            first_batch_times.append(elapsed)
        if i >= last_batch_start:
            last_batch_times.append(elapsed)
        if i % RSS_SAMPLE_INTERVAL == 0:
            rss_samples_kb.append(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    chain.close()
    rss_samples_kb.append(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    first_avg_ms = 1000.0 * sum(first_batch_times) / len(first_batch_times)
    last_avg_ms = 1000.0 * sum(last_batch_times) / len(last_batch_times)

    # 最初のサンプル(起動直後、モデル読み込み等の一時的な割り当てを含む)ではなく、
    # 10%進んだ時点を「ウォームアップ後」のベースラインとして使う。
    warm_index = max(1, len(rss_samples_kb) // 10)
    warm_rss_kb = rss_samples_kb[warm_index]
    final_rss_kb = rss_samples_kb[-1]

    return {
        "n_frames": n_frames,
        "rss_samples_kb": rss_samples_kb,
        "warm_rss_kb": warm_rss_kb,
        "final_rss_kb": final_rss_kb,
        "rss_growth_ratio": final_rss_kb / warm_rss_kb if warm_rss_kb > 0 else float("inf"),
        "first_batch_avg_ms": first_avg_ms,
        "last_batch_avg_ms": last_avg_ms,
        "timing_ratio": last_avg_ms / first_avg_ms if first_avg_ms > 0 else float("inf"),
    }


def test_soak_memory_and_timing_stable_over_100k_frames():
    if resource is None:
        import pytest

        pytest.skip("resource module unavailable on this platform (POSIX-only soak test)")

    result = run_soak_test()

    assert result["rss_growth_ratio"] < RSS_GROWTH_RATIO_THRESHOLD, (
        f"RSS grew from {result['warm_rss_kb']}KB (10% mark) to {result['final_rss_kb']}KB "
        f"(ratio {result['rss_growth_ratio']:.2f}, threshold {RSS_GROWTH_RATIO_THRESHOLD}) "
        "-- possible memory leak"
    )
    assert result["timing_ratio"] < TIMING_SLOWDOWN_RATIO_THRESHOLD, (
        f"per-frame processing time grew from {result['first_batch_avg_ms']:.4f}ms to "
        f"{result['last_batch_avg_ms']:.4f}ms (ratio {result['timing_ratio']:.2f}, "
        f"threshold {TIMING_SLOWDOWN_RATIO_THRESHOLD})"
    )


def main() -> None:
    result = run_soak_test()
    print(f"frames processed          : {result['n_frames']}")
    print(f"RSS samples (KB, every {RSS_SAMPLE_INTERVAL} frames): {result['rss_samples_kb']}")
    print(f"RSS warm(10%) -> final     : {result['warm_rss_kb']} KB -> {result['final_rss_kb']} KB")
    print(f"RSS growth ratio           : {result['rss_growth_ratio']:.3f}")
    print(f"first {TIMING_BATCH_SIZE} avg ms/frame : {result['first_batch_avg_ms']:.4f}")
    print(f"last {TIMING_BATCH_SIZE} avg ms/frame  : {result['last_batch_avg_ms']:.4f}")
    print(f"timing ratio (last/first)  : {result['timing_ratio']:.3f}")


if __name__ == "__main__":
    main()

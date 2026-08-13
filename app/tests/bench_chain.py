"""VoiceChainの処理速度ベンチマーク。

1フレーム=10msの予算に対し、実処理時間が十分な余裕(目安: 予算の30%未満)を
持っていることを確認する。`python -m tests.bench_chain`で数値を表示できるほか、
pytest経由でも実行できる(`pytest tests/bench_chain.py`)。
"""

from __future__ import annotations

import time

import numpy as np

from soloclarity.dsp.chain import FRAME_SIZE, SAMPLE_RATE, VoiceChain
from tests._rnnoise_test_lib import find_rnnoise_test_library_path

N_FRAMES = 1000
FRAME_BUDGET_MS = 1000.0 * FRAME_SIZE / SAMPLE_RATE  # 10.0ms
BUDGET_USAGE_RATIO_THRESHOLD = 0.30  # 実処理時間は予算の30%未満であることを期待する


def run_benchmark(preset_name: str = "quiet_low_voice") -> dict:
    library_path = find_rnnoise_test_library_path()
    chain = VoiceChain(preset_name, rnnoise_library_path=library_path)

    rng = np.random.default_rng(0)
    frames = []
    for i in range(N_FRAMES):
        t = (np.arange(FRAME_SIZE) + i * FRAME_SIZE) / SAMPLE_RATE
        tone = 0.1 * np.sin(2 * np.pi * 180 * t)
        noise = rng.normal(0.0, 0.01, FRAME_SIZE)
        frames.append((tone + noise).astype(np.float32))

    # ウォームアップ(JIT的な初回コスト・キャッシュ効果を除外する)
    for frame in frames[:20]:
        chain.process(frame)

    start = time.perf_counter()
    for frame in frames:
        chain.process(frame)
    elapsed_s = time.perf_counter() - start
    chain.close()

    avg_ms_per_frame = (elapsed_s * 1000.0) / N_FRAMES
    budget_usage_ratio = avg_ms_per_frame / FRAME_BUDGET_MS
    return {
        "n_frames": N_FRAMES,
        "total_seconds": elapsed_s,
        "avg_ms_per_frame": avg_ms_per_frame,
        "frame_budget_ms": FRAME_BUDGET_MS,
        "budget_usage_ratio": budget_usage_ratio,
    }


def test_bench_chain_within_budget():
    result = run_benchmark()
    assert result["budget_usage_ratio"] < BUDGET_USAGE_RATIO_THRESHOLD, (
        f"average frame processing time {result['avg_ms_per_frame']:.3f}ms "
        f"uses {result['budget_usage_ratio']*100:.1f}% of the {FRAME_BUDGET_MS}ms budget "
        f"(threshold {BUDGET_USAGE_RATIO_THRESHOLD*100:.0f}%)"
    )


def main() -> None:
    result = run_benchmark()
    print(f"frames processed        : {result['n_frames']}")
    print(f"total time              : {result['total_seconds']:.4f} s")
    print(f"avg time per frame      : {result['avg_ms_per_frame']:.4f} ms")
    print(f"frame budget (10ms)     : {result['frame_budget_ms']:.4f} ms")
    print(f"budget usage            : {result['budget_usage_ratio']*100:.1f} %")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass

import httpx


@dataclass(slots=True)
class LatencyStats:
    count: int
    min_ms: float
    median_ms: float
    p95_ms: float
    max_ms: float
    mean_ms: float


def compute_stats(values: list[float]) -> LatencyStats:
    ordered = sorted(values)
    if not ordered:
        return LatencyStats(count=0, min_ms=0.0, median_ms=0.0, p95_ms=0.0, max_ms=0.0, mean_ms=0.0)
    p95_index = min(len(ordered) - 1, max(0, round(len(ordered) * 0.95) - 1))
    return LatencyStats(
        count=len(ordered),
        min_ms=round(ordered[0], 2),
        median_ms=round(statistics.median(ordered), 2),
        p95_ms=round(ordered[p95_index], 2),
        max_ms=round(ordered[-1], 2),
        mean_ms=round(statistics.mean(ordered), 2),
    )


def log_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def create_ephemeral_api_key(base_url: str, admin_secret: str, credits: float) -> str:
    timestamp = int(time.time())
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        account = client.post(
            "/admin/accounts",
            headers={"x-admin-secret": admin_secret},
            json={"name": f"bench-account-{timestamp}"},
        )
        account.raise_for_status()
        account_id = account.json()["id"]
        adjust = client.post(
            f"/admin/accounts/{account_id}/credits/adjust",
            headers={"x-admin-secret": admin_secret},
            json={"credits_delta": credits, "notes": "benchmark credits"},
        )
        adjust.raise_for_status()
        key = client.post(
            "/admin/api-keys",
            headers={"x-admin-secret": admin_secret},
            json={"account_id": account_id, "name": f"bench-key-{timestamp}"},
        )
        key.raise_for_status()
        return key.json()["api_key"]


def benchmark_models(base_url: str, api_key: str) -> float:
    started = time.perf_counter()
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        response = client.get("/v1/models", headers={"authorization": f"Bearer {api_key}"})
        response.raise_for_status()
    return (time.perf_counter() - started) * 1000


def benchmark_non_stream(base_url: str, api_key: str, model: str, prompt: str) -> float:
    started = time.perf_counter()
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        response.raise_for_status()
    return (time.perf_counter() - started) * 1000


def benchmark_stream(base_url: str, api_key: str, model: str, prompt: str) -> tuple[float, float]:
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        started = time.perf_counter()
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            first_chunk_ms: float | None = None
            for chunk in response.iter_text():
                if not chunk:
                    continue
                if first_chunk_ms is None and "data:" in chunk:
                    first_chunk_ms = (time.perf_counter() - started) * 1000
            total_ms = (time.perf_counter() - started) * 1000
    return (first_chunk_ms or total_ms, total_ms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the local AgentHub gateway.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--admin-secret", default="change-me")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--bootstrap-credits", type=float, default=100.0)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", default="Say OK and nothing else.")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    args = parser.parse_args()

    api_key = args.api_key or create_ephemeral_api_key(args.base_url, args.admin_secret, args.bootstrap_credits)
    log_progress(f"benchmarking {args.model} against {args.base_url}")

    for index in range(args.warmup):
        log_progress(f"warmup {index + 1}/{args.warmup}: non-stream")
        benchmark_non_stream(args.base_url, api_key, args.model, args.prompt)
        log_progress(f"warmup {index + 1}/{args.warmup}: stream")
        benchmark_stream(args.base_url, api_key, args.model, args.prompt)

    models_latencies: list[float] = []
    for index in range(args.iterations):
        log_progress(f"iteration {index + 1}/{args.iterations}: /v1/models")
        models_latencies.append(benchmark_models(args.base_url, api_key))

    non_stream_latencies: list[float] = []
    for index in range(args.iterations):
        log_progress(f"iteration {index + 1}/{args.iterations}: non-stream")
        non_stream_latencies.append(benchmark_non_stream(args.base_url, api_key, args.model, args.prompt))

    first_chunk_latencies: list[float] = []
    total_stream_latencies: list[float] = []
    for index in range(args.iterations):
        log_progress(f"iteration {index + 1}/{args.iterations}: stream")
        first_chunk_ms, total_ms = benchmark_stream(args.base_url, api_key, args.model, args.prompt)
        first_chunk_latencies.append(first_chunk_ms)
        total_stream_latencies.append(total_ms)

    result = {
        "base_url": args.base_url,
        "model": args.model,
        "iterations": args.iterations,
        "api_key": api_key,
        "models_ms": asdict(compute_stats(models_latencies)),
        "non_stream_ms": asdict(compute_stats(non_stream_latencies)),
        "stream_first_chunk_ms": asdict(compute_stats(first_chunk_latencies)),
        "stream_total_ms": asdict(compute_stats(total_stream_latencies)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

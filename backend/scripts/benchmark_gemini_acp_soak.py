from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from dataclasses import asdict

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_gateway import compute_stats, create_ephemeral_api_key, log_progress


def parse_pid_lines(raw: str) -> list[int]:
    pids: list[int] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            continue
    return pids


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


def find_gemini_acp_children(backend_pid: int) -> list[int]:
    result = subprocess.run(
        ["pgrep", "-P", str(backend_pid), "-f", "gemini --acp"],
        capture_output=True,
        text=True,
        check=False,
    )
    return parse_pid_lines(result.stdout)


def kill_gemini_acp_children(backend_pid: int) -> int:
    child_pids = find_gemini_acp_children(backend_pid)
    for pid in child_pids:
        try:
            subprocess.run(["kill", str(pid)], check=False, capture_output=True, text=True)
        except Exception:
            continue
    return len(child_pids)


def build_soak_report(
    *,
    model: str,
    sequential_latencies_ms: list[float],
    recovery_latencies_ms: list[float],
    killed_children: list[int],
) -> dict[str, object]:
    cold = sequential_latencies_ms[:1]
    warm = sequential_latencies_ms[1:]
    return {
        "model": model,
        "sequential_requests": len(sequential_latencies_ms),
        "cold_start_ms": asdict(compute_stats(cold)),
        "warm_path_ms": asdict(compute_stats(warm)),
        "recovery_cycles": len(recovery_latencies_ms),
        "recovery_ms": asdict(compute_stats(recovery_latencies_ms)),
        "killed_children": killed_children,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Gemini ACP warm-path and recovery behavior.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--admin-secret", default="change-me")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--bootstrap-credits", type=float, default=100.0)
    parser.add_argument("--model", default="gemini:gemini-2.5-flash")
    parser.add_argument("--prompt", default="Say OK and nothing else.")
    parser.add_argument("--sequential-requests", type=int, default=4)
    parser.add_argument("--recovery-cycles", type=int, default=0)
    parser.add_argument("--backend-pid", type=int, default=None)
    args = parser.parse_args()

    if args.recovery_cycles > 0 and not args.backend_pid:
        raise SystemExit("--backend-pid is required when --recovery-cycles is greater than zero")

    api_key = args.api_key or create_ephemeral_api_key(args.base_url, args.admin_secret, args.bootstrap_credits)
    sequential_latencies_ms: list[float] = []
    recovery_latencies_ms: list[float] = []
    killed_children: list[int] = []

    log_progress(f"soak benchmarking {args.model} against {args.base_url}")
    for index in range(args.sequential_requests):
        log_progress(f"sequential request {index + 1}/{args.sequential_requests}")
        sequential_latencies_ms.append(benchmark_non_stream(args.base_url, api_key, args.model, args.prompt))

    for index in range(args.recovery_cycles):
        log_progress(f"recovery cycle {index + 1}/{args.recovery_cycles}: killing gemini ACP child")
        assert args.backend_pid is not None
        killed_count = kill_gemini_acp_children(args.backend_pid)
        killed_children.append(killed_count)
        time.sleep(0.5)
        log_progress(f"recovery cycle {index + 1}/{args.recovery_cycles}: probing recovery")
        recovery_latencies_ms.append(benchmark_non_stream(args.base_url, api_key, args.model, args.prompt))

    report = build_soak_report(
        model=args.model,
        sequential_latencies_ms=sequential_latencies_ms,
        recovery_latencies_ms=recovery_latencies_ms,
        killed_children=killed_children,
    )
    report["base_url"] = args.base_url
    report["api_key"] = api_key
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

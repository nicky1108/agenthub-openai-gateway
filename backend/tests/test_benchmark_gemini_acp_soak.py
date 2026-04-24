from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_gemini_acp_soak.py"
    spec = importlib.util.spec_from_file_location("benchmark_gemini_acp_soak", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_pid_lines_accepts_numeric_rows() -> None:
    module = load_module()

    assert module.parse_pid_lines("123\n456\n") == [123, 456]
    assert module.parse_pid_lines("123\njunk\n456\n") == [123, 456]
    assert module.parse_pid_lines("") == []


def test_build_soak_report_splits_cold_warm_and_recovery() -> None:
    module = load_module()

    report = module.build_soak_report(
        model="gemini:gemini-2.5-flash",
        sequential_latencies_ms=[15000.0, 1800.0, 1700.0],
        recovery_latencies_ms=[14000.0, 13500.0],
        killed_children=[1, 1],
    )

    assert report["model"] == "gemini:gemini-2.5-flash"
    assert report["cold_start_ms"]["count"] == 1
    assert report["cold_start_ms"]["median_ms"] == 15000.0
    assert report["warm_path_ms"]["count"] == 2
    assert report["warm_path_ms"]["median_ms"] == 1750.0
    assert report["recovery_ms"]["count"] == 2
    assert report["recovery_ms"]["median_ms"] == 13750.0
    assert report["killed_children"] == [1, 1]


def test_benchmark_queue_concurrency_reports_request_and_round_stats() -> None:
    module = load_module()

    def fake_non_stream(*_args, **_kwargs) -> float:
        return 25.0

    module.benchmark_non_stream = fake_non_stream

    report = module.benchmark_queue_concurrency(
        base_url="http://127.0.0.1:8787",
        api_key="bench-key",
        model="gemini:gemini-2.5-flash",
        prompt="hello",
        concurrency_levels=[2, 4],
        rounds=3,
    )

    assert sorted(report.keys()) == ["2", "4"]
    assert report["2"]["requests"] == 6
    assert report["2"]["rounds"] == 3
    assert report["2"]["request_ms"]["count"] == 6
    assert report["2"]["request_ms"]["median_ms"] == 25.0
    assert report["2"]["round_wall_ms"]["count"] == 3
    assert report["4"]["requests"] == 12

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_benchmark_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_gateway.py"
    spec = importlib.util.spec_from_file_location("benchmark_gateway", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_concurrency_levels_accepts_csv() -> None:
    module = load_benchmark_module()

    assert module.parse_concurrency_levels(None) == []
    assert module.parse_concurrency_levels("") == []
    assert module.parse_concurrency_levels("2,4,8") == [2, 4, 8]


def test_parse_concurrency_levels_rejects_invalid_values() -> None:
    module = load_benchmark_module()

    try:
        module.parse_concurrency_levels("0,2")
    except ValueError as exc:
        assert "positive integers" in str(exc)
    else:
        raise AssertionError("expected parse_concurrency_levels to reject non-positive values")


def test_benchmark_concurrency_runs_each_request_and_reports_counts() -> None:
    module = load_benchmark_module()

    def fake_non_stream(*_args, **_kwargs) -> float:
        return 10.0

    def fake_stream(*_args, **_kwargs) -> tuple[float, float]:
        return (20.0, 30.0)

    module.benchmark_non_stream = fake_non_stream
    module.benchmark_stream = fake_stream

    report = module.benchmark_concurrency(
        base_url="http://127.0.0.1:8787",
        api_key="bench-key",
        model="codex:gpt-5.4",
        prompt="hi",
        concurrency_levels=[2, 4],
        iterations=3,
    )

    assert sorted(report.keys()) == ["2", "4"]
    assert report["2"].non_stream_ms.count == 6
    assert report["2"].stream_first_chunk_ms.count == 6
    assert report["2"].stream_total_ms.count == 6
    assert report["4"].non_stream_ms.count == 12
    assert report["4"].stream_first_chunk_ms.median_ms == 20.0
    assert report["4"].stream_total_ms.median_ms == 30.0

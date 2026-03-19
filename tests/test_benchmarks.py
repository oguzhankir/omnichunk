# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BENCH = Path(__file__).resolve().parents[1] / "benchmarks"
if str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

from comparison_format import (
    aggregate_tool_totals,
    build_comparison_json_payload,
    comparison_exit_code,
    format_comparison_summary_table,
    format_scenario_benchmark_table,
    format_speedup_lines,
)


class _Row:
    __slots__ = ("data_bytes", "seconds", "status")

    def __init__(self, data_bytes: int, seconds: float, status: str) -> None:
        self.data_bytes = data_bytes
        self.seconds = seconds
        self.status = status


def test_aggregate_tool_totals_ok_and_unavailable() -> None:
    rows = {
        "omnichunk": [_Row(1000, 0.1, "ok"), _Row(2000, 0.2, "ok")],
        "langchain_recursive": [_Row(1000, 0.0, "unavailable")],
    }
    agg = aggregate_tool_totals(tool_rows=rows)
    assert agg["omnichunk"]["status"] == "ok"
    assert agg["omnichunk"]["total_seconds"] == pytest.approx(0.3)
    assert agg["langchain_recursive"]["status"] == "unavailable"


def test_format_comparison_summary_table_skip_and_winner() -> None:
    agg = {
        "omnichunk": {
            "total_seconds": 0.1,
            "total_mbps": 10.0,
            "total_mb": 1.0,
            "status": "ok",
        },
        "langchain_recursive": {
            "total_seconds": 0.5,
            "total_mbps": 2.0,
            "total_mb": 1.0,
            "status": "ok",
        },
        "semantic_text_splitter": {
            "total_seconds": 0.0,
            "total_mbps": 0.0,
            "total_mb": 0.0,
            "status": "unavailable",
        },
    }
    text = format_comparison_summary_table(
        tool_order=["omnichunk", "langchain_recursive", "semantic_text_splitter"],
        aggregates=agg,
    )
    assert "SKIP" in text
    assert "✓" in text
    assert "omnichunk" in text


def test_format_speedup_lines_and_no_baseline() -> None:
    agg = {
        "omnichunk": {"total_seconds": 0.2, "status": "ok", "total_mbps": 1.0, "total_mb": 1.0},
        "other": {"total_seconds": 0.4, "status": "ok", "total_mbps": 1.0, "total_mb": 1.0},
    }
    lines = format_speedup_lines(
        omnichunk_seconds=0.2,
        aggregates=agg,
        tool_order=["omnichunk", "other"],
    )
    assert any("2" in ln and "×" in ln for ln in lines)

    empty = format_speedup_lines(
        omnichunk_seconds=0.0,
        aggregates=agg,
        tool_order=["omnichunk", "other"],
    )
    assert empty == ["No baseline available"]


def test_format_speedup_lines_small_ratio_not_rounded_to_zero() -> None:
    """Regression: .1f made competitor/omnichunk < 0.05 print as 0.0×."""
    agg = {
        "omnichunk": {"total_seconds": 0.00654, "status": "ok", "total_mbps": 1.0, "total_mb": 1.0},
        "langchain_recursive": {
            "total_seconds": 0.000108,
            "status": "ok",
            "total_mbps": 1.0,
            "total_mb": 1.0,
        },
    }
    lines = format_speedup_lines(
        omnichunk_seconds=0.00654,
        aggregates=agg,
        tool_order=["omnichunk", "langchain_recursive"],
    )
    joined = "\n".join(lines)
    assert "0.0×" not in joined
    assert "0.0165" in joined or "0.016" in joined


def test_comparison_exit_code_within_five_percent() -> None:
    agg = {
        "omnichunk": {"total_seconds": 1.05, "status": "ok", "total_mbps": 1.0, "total_mb": 1.0},
        "langchain_recursive": {
            "total_seconds": 1.0,
            "status": "ok",
            "total_mbps": 1.0,
            "total_mb": 1.0,
        },
    }
    order = ["omnichunk", "langchain_recursive"]
    assert comparison_exit_code(aggregates=agg, tool_order=order) == 0

    agg_slow = {
        "omnichunk": {"total_seconds": 2.0, "status": "ok", "total_mbps": 1.0, "total_mb": 1.0},
        "langchain_recursive": {
            "total_seconds": 1.0,
            "status": "ok",
            "total_mbps": 1.0,
            "total_mb": 1.0,
        },
    }
    assert comparison_exit_code(aggregates=agg_slow, tool_order=order) == 1


def test_comparison_exit_code_no_ok_competitor() -> None:
    agg = {
        "omnichunk": {"total_seconds": 0.5, "status": "ok", "total_mbps": 1.0, "total_mb": 1.0},
        "langchain_recursive": {
            "total_seconds": 0.0,
            "status": "unavailable",
            "total_mbps": 0.0,
            "total_mb": 0.0,
        },
    }
    order = ["omnichunk", "langchain_recursive"]
    assert comparison_exit_code(aggregates=agg, tool_order=order) == 0


def test_build_comparison_json_payload_order() -> None:
    agg = {
        "omnichunk": {"total_seconds": 0.1, "status": "ok", "total_mbps": 9.0, "total_mb": 1.0},
        "langchain_recursive": {
            "total_seconds": 0.4,
            "status": "ok",
            "total_mbps": 2.0,
            "total_mb": 1.0,
        },
    }
    payload = build_comparison_json_payload(
        scenario_names=["a", "b"],
        tool_order=["omnichunk", "langchain_recursive"],
        aggregates=agg,
        winner="omnichunk",
    )
    assert list(payload.keys()) == ["timestamp", "scenarios", "tools", "speedup", "winner"]
    assert payload["scenarios"] == ["a", "b"]
    assert payload["winner"] == "omnichunk"
    assert payload["speedup"]["omnichunk_vs_langchain_recursive"] == pytest.approx(4.0)


def test_format_scenario_benchmark_table() -> None:
    rows = [
        ("python_complex", 1024, 5, 0.001, 1.0),
        ("markdown_doc", 2048, 8, 0.002, 2.0),
    ]
    text = format_scenario_benchmark_table(rows)
    assert "python_complex" in text
    assert "TOTAL" in text
    assert "Chunks" in text

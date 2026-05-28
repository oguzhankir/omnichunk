from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_benchmarks  # noqa: E402,PLC2701


def test_gate_first_run_no_baseline_skips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No baseline file → exit 0 with a skip message, no file written."""
    baseline = tmp_path / "baseline.json"
    rc = check_benchmarks.run_regression_gate(
        update_baseline=False,
        baseline_path=baseline,
        measure_fn=lambda: 42.0,
    )
    assert rc == 0
    assert not baseline.exists()
    out = capsys.readouterr().out
    assert "skipping regression check" in out


def test_gate_passes_when_above_threshold(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture": "tests/fixtures/python_complex.py",
                "metric": "mbps",
                "repeat": 3,
                "history": [1.0, 1.0, 1.0],
                "median_mbps": 1.0,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    rc = check_benchmarks.run_regression_gate(
        update_baseline=False,
        baseline_path=baseline,
        measure_fn=lambda: 50.0,
    )
    assert rc == 0


def test_gate_fails_when_below_threshold(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture": "tests/fixtures/python_complex.py",
                "metric": "mbps",
                "repeat": 3,
                "history": [100.0, 100.0, 100.0],
                "median_mbps": 100.0,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    rc = check_benchmarks.run_regression_gate(
        update_baseline=False,
        baseline_path=baseline,
        measure_fn=lambda: 50.0,
    )
    assert rc == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "below baseline median" in out


def test_update_baseline_writes_history_window(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture": "tests/fixtures/python_complex.py",
                "metric": "mbps",
                "repeat": 3,
                "history": [10.0, 11.0, 12.0, 13.0, 14.0],
                "median_mbps": 12.0,
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    rc = check_benchmarks.run_regression_gate(
        update_baseline=True,
        baseline_path=baseline,
        measure_fn=lambda: 20.0,
    )
    assert rc == 0

    updated = json.loads(baseline.read_text(encoding="utf-8"))
    assert updated["history"] == [11.0, 12.0, 13.0, 14.0, 20.0]
    expected_median = statistics.median([11.0, 12.0, 13.0, 14.0, 20.0])
    assert updated["median_mbps"] == pytest.approx(expected_median)
    assert updated["schema_version"] == 1
    assert updated["fixture"] == "tests/fixtures/python_complex.py"


def test_update_baseline_first_run_writes_singleton(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    rc = check_benchmarks.run_regression_gate(
        update_baseline=True,
        baseline_path=baseline,
        measure_fn=lambda: 33.0,
    )
    assert rc == 0
    assert baseline.is_file()
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    assert payload["history"] == [33.0]
    assert payload["median_mbps"] == pytest.approx(33.0)

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


def test_release_gate_rejects_missing_baseline(tmp_path: Path) -> None:
    assert (
        check_benchmarks.run_regression_gate(
            update_baseline=False,
            baseline_path=tmp_path / "missing.json",
            measure_fn=lambda: 10.0,
            require_baseline=True,
        )
        == 1
    )


@pytest.mark.parametrize("measurement", [float("nan"), float("inf"), 0.0, -1.0])
def test_nonfinite_or_nonpositive_measurements_fail(tmp_path: Path, measurement: float) -> None:
    assert (
        check_benchmarks.run_regression_gate(
            update_baseline=True,
            baseline_path=tmp_path / "baseline.json",
            measure_fn=lambda: measurement,
        )
        == 1
    )


@pytest.mark.parametrize(
    "change,status",
    [
        ({"bytes_per_second": 5.0}, "regression"),
        ({"bytes_per_second": float("nan")}, "invalid_measurement"),
        ({"max_chars": 513}, "invalid_output"),
        ({"reconstruction": False}, "invalid_output"),
        ({"dependencies": {"tree-sitter": "different"}}, "different_dependencies"),
        ({"bytes_per_second": 10.0}, "passed"),
    ],
)
def test_reference_comparison_requires_fair_validated_outputs(change: dict, status: str) -> None:
    baseline = {
        "bytes_per_second": 10.0,
        "reconstruction": True,
        "max_chars": 512,
        "dependencies": {"tree-sitter": "same"},
    }
    candidate = {**baseline, **change}
    assert check_benchmarks.reference_comparison_status(baseline, candidate) == status


def test_invalid_baseline_reference_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def failure(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "git rev-parse")

    monkeypatch.setattr(check_benchmarks.subprocess, "run", failure)
    assert check_benchmarks.run_reference_gate("missing-ref") == 1


def transition_pair() -> tuple[dict, dict]:
    candidate = {
        "bytes_per_second": 10.0,
        "max_chars": 500,
        "reconstruction": True,
        "dependencies": {"tree-sitter": "same"},
    }
    report = {
        "baseline_revision": "old-invalid-commit",
        "candidate_source_sha256": "new-code",
        "project_config_sha256": "dependency-config",
        "fixture_sha256": "frozen-corpus",
        "harness_sha256": "frozen-harness",
        "settings": {"max_size": 512},
        "status": "invalid_output",
        "baseline": {**candidate, "max_chars": 768},
        "candidate": candidate,
    }
    manifest = {
        **report,
        "schema_version": 1,
        "rationale": "Old output exceeds the budget; establish a new exact-budget baseline.",
    }
    return manifest, report


def test_transition_exception_keeps_old_failure_explicit() -> None:
    manifest, report = transition_pair()
    check_benchmarks.validate_transition_manifest(manifest, report, "v2.1.0")
    assert report["status"] == "invalid_output"
    assert report["baseline"]["max_chars"] == 768


@pytest.mark.parametrize(
    "field,value",
    [
        ("baseline_revision", "different-commit"),
        ("candidate_source_sha256", "changed-code"),
        ("project_config_sha256", "changed-dependencies"),
        ("fixture_sha256", "changed-corpus"),
        ("harness_sha256", "changed-harness"),
        ("settings", {"max_size": 1000}),
    ],
)
def test_transition_exception_rejects_unreviewed_drift(field: str, value: object) -> None:
    manifest, report = transition_pair()
    report[field] = value
    with pytest.raises(ValueError, match="no longer matches"):
        check_benchmarks.validate_transition_manifest(manifest, report, "v2.1.0")


@pytest.mark.parametrize("tag", [None, "v1.0.0", "v3.0.0", "main"])
def test_transition_exception_requires_an_explicit_2x_release(tag: str | None) -> None:
    manifest, report = transition_pair()
    with pytest.raises(ValueError, match="tagged 2.x"):
        check_benchmarks.validate_transition_manifest(manifest, report, tag)


def test_transition_cannot_excuse_invalid_candidate_or_speed_regression() -> None:
    manifest, report = transition_pair()
    report["candidate"]["max_chars"] = 900
    with pytest.raises(ValueError, match="new contract"):
        check_benchmarks.validate_transition_manifest(manifest, report, "v2.1.0")
    manifest, report = transition_pair()
    report["status"] = "regression"
    with pytest.raises(ValueError, match="only.*invalid old contract"):
        check_benchmarks.validate_transition_manifest(manifest, report, "v2.1.0")

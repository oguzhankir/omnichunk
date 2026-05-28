from __future__ import annotations

import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BENCH_SCRIPT = ROOT / "benchmarks" / "run_benchmarks.py"
COMPARE_SCRIPT = ROOT / "benchmarks" / "run_comparisons.py"
QUALITY_SCRIPT = ROOT / "benchmarks" / "run_quality_report.py"
HTML_REPORT_SCRIPT = ROOT / "benchmarks" / "run_html_report.py"
LARGE_CORPUS_SCRIPT = ROOT / "benchmarks" / "run_large_corpus.py"
HOTSPOT_PROFILE_SCRIPT = ROOT / "benchmarks" / "run_hotspot_profile.py"

BASELINE_PATH = ROOT / "benchmarks" / "baseline.json"
BASELINE_FIXTURE = "tests/fixtures/python_complex.py"
HISTORY_WINDOW = 5
REGRESSION_THRESHOLD = 0.90  # fail if measured < median * 0.90 (>10% slowdown)
DEFAULT_REPEAT = 3
SCHEMA_VERSION = 1


def _flag_value(flag: str) -> str | None:
    for i, arg in enumerate(sys.argv):
        if arg == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _load_baseline(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"baseline file is corrupt ({exc}); treating as missing")
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_baseline(path: Path, history: list[float]) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "fixture": BASELINE_FIXTURE,
        "metric": "mbps",
        "repeat": DEFAULT_REPEAT,
        "history": [round(x, 4) for x in history],
        "median_mbps": round(statistics.median(history), 4),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _measure_mbps() -> float:
    """Defer import so the rest of the dispatcher works without omnichunk installed."""
    bench_dir = ROOT / "benchmarks"
    src_dir = ROOT / "src"
    for p in (bench_dir, src_dir):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    from run_benchmarks import measure_python_complex_mbps  # noqa: PLC0415

    return measure_python_complex_mbps(repeat=DEFAULT_REPEAT)


def run_regression_gate(
    *,
    update_baseline: bool,
    baseline_path: Path = BASELINE_PATH,
    measure_fn: Any = None,
) -> int:
    """Throughput regression gate. See module docstring for semantics."""
    measure = measure_fn if measure_fn is not None else _measure_mbps
    measured = float(measure())
    print(f"throughput-gate: measured python_complex throughput = {measured:.3f} MB/s")

    baseline = _load_baseline(baseline_path)

    if baseline is None:
        print(
            "throughput-gate: no baseline.json found — skipping regression check "
            "(first run on this branch)."
        )
        if update_baseline:
            written = _write_baseline(baseline_path, [measured])
            print(f"throughput-gate: wrote initial baseline ({written['median_mbps']} MB/s)")
        return 0

    history_raw = baseline.get("history") or []
    history: list[float] = [float(x) for x in history_raw if isinstance(x, int | float)]
    median_baseline = float(
        baseline.get("median_mbps", statistics.median(history) if history else 0.0)
    )
    threshold = median_baseline * REGRESSION_THRESHOLD

    print(
        f"throughput-gate: baseline median = {median_baseline:.3f} MB/s "
        f"(threshold = {threshold:.3f} MB/s, "
        f"history n={len(history)})"
    )

    if measured < threshold:
        drop_pct = (1.0 - measured / median_baseline) * 100.0 if median_baseline > 0 else 0.0
        print(
            f"throughput-gate: FAIL — measured {measured:.3f} MB/s is "
            f"{drop_pct:.1f}% below baseline median {median_baseline:.3f} MB/s"
        )
        return 1

    print("throughput-gate: PASS")

    if update_baseline:
        new_history = (history + [measured])[-HISTORY_WINDOW:]
        written = _write_baseline(baseline_path, new_history)
        print(
            f"throughput-gate: baseline updated "
            f"(history n={len(written['history'])}, median={written['median_mbps']} MB/s)"
        )

    return 0


def main() -> int:
    missing: list[str] = []
    for path in (
        BENCH_SCRIPT,
        COMPARE_SCRIPT,
        QUALITY_SCRIPT,
        HTML_REPORT_SCRIPT,
        LARGE_CORPUS_SCRIPT,
        HOTSPOT_PROFILE_SCRIPT,
    ):
        if not path.exists():
            missing.append(str(path.relative_to(ROOT)))

    if missing:
        print("Missing benchmark script(s):")
        for rel in missing:
            print(f"- {rel}")
        return 1

    should_run_benchmark = "--run" in sys.argv
    should_run_compare = "--run-compare" in sys.argv
    should_run_compare_extra = "--run-compare-extra" in sys.argv
    should_run_quality = "--run-quality" in sys.argv
    should_run_large_corpus = "--run-large-corpus" in sys.argv
    should_run_profile = "--run-profile" in sys.argv
    should_run_regression_gate = "--run-regression-gate" in sys.argv
    update_baseline_flag = "--update-baseline" in sys.argv
    html_report_path = _flag_value("--html-report")

    if not (
        should_run_benchmark
        or should_run_compare
        or should_run_compare_extra
        or should_run_quality
        or should_run_large_corpus
        or should_run_profile
        or should_run_regression_gate
        or html_report_path is not None
    ):
        print(
            "Benchmark scripts are present. Use --run, --run-compare, --run-compare-extra, "
            "--run-quality, --run-large-corpus, --run-profile, --run-regression-gate "
            "[--update-baseline], or --html-report PATH."
        )
        return 0

    exit_code = 0

    if should_run_benchmark:
        result = subprocess.run(
            [sys.executable, str(BENCH_SCRIPT)],
            cwd=str(ROOT),
            check=False,
        )
        exit_code = max(exit_code, int(result.returncode))

    if should_run_compare:
        result = subprocess.run(
            [sys.executable, str(COMPARE_SCRIPT)],
            cwd=str(ROOT),
            check=False,
        )
        exit_code = max(exit_code, int(result.returncode))

    if should_run_compare_extra:
        result = subprocess.run(
            [sys.executable, str(COMPARE_SCRIPT), "--include-extra"],
            cwd=str(ROOT),
            check=False,
        )
        exit_code = max(exit_code, int(result.returncode))

    if should_run_quality:
        result = subprocess.run(
            [sys.executable, str(QUALITY_SCRIPT)],
            cwd=str(ROOT),
            check=False,
        )
        exit_code = max(exit_code, int(result.returncode))

    if should_run_large_corpus:
        result = subprocess.run(
            [
                sys.executable,
                str(LARGE_CORPUS_SCRIPT),
                "--mode",
                "fixtures",
                "--repeat",
                "4",
                "--top-slowest",
                "3",
            ],
            cwd=str(ROOT),
            check=False,
        )
        exit_code = max(exit_code, int(result.returncode))

    if should_run_profile:
        result = subprocess.run(
            [
                sys.executable,
                str(HOTSPOT_PROFILE_SCRIPT),
                "--mode",
                "fixtures",
                "--repeat",
                "3",
                "--limit",
                "10",
            ],
            cwd=str(ROOT),
            check=False,
        )
        exit_code = max(exit_code, int(result.returncode))

    if should_run_regression_gate:
        gate_rc = run_regression_gate(update_baseline=update_baseline_flag)
        exit_code = max(exit_code, int(gate_rc))

    if html_report_path is not None:
        result = subprocess.run(
            [sys.executable, str(HTML_REPORT_SCRIPT), "--output", html_report_path],
            cwd=str(ROOT),
            check=False,
        )
        exit_code = max(exit_code, int(result.returncode))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

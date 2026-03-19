from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_SCRIPT = ROOT / "benchmarks" / "run_benchmarks.py"
COMPARE_SCRIPT = ROOT / "benchmarks" / "run_comparisons.py"
QUALITY_SCRIPT = ROOT / "benchmarks" / "run_quality_report.py"
HTML_REPORT_SCRIPT = ROOT / "benchmarks" / "run_html_report.py"
LARGE_CORPUS_SCRIPT = ROOT / "benchmarks" / "run_large_corpus.py"
HOTSPOT_PROFILE_SCRIPT = ROOT / "benchmarks" / "run_hotspot_profile.py"


def _flag_value(flag: str) -> str | None:
    for i, arg in enumerate(sys.argv):
        if arg == flag and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


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
    html_report_path = _flag_value("--html-report")

    if not (
        should_run_benchmark
        or should_run_compare
        or should_run_compare_extra
        or should_run_quality
        or should_run_large_corpus
        or should_run_profile
        or html_report_path is not None
    ):
        print(
            "Benchmark scripts are present. Use --run, --run-compare, --run-compare-extra, "
            "--run-quality, --run-large-corpus, --run-profile, or --html-report PATH."
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

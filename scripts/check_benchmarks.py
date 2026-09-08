from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import statistics
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from io import BytesIO
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
REGRESSION_THRESHOLD = 0.90
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
    """Defer import so the dispatcher works without omnichunk installed."""
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
    require_baseline: bool = False,
) -> int:
    """Throughput regression gate.

    - No baseline → exit 0 (skip), optionally seed it when --update-baseline.
    - Measured < median × 0.90 → exit 1 (regression).
    - Otherwise exit 0, rolling-window update when --update-baseline.
    """
    measure = measure_fn if measure_fn is not None else _measure_mbps
    measured = float(measure())
    if not math.isfinite(measured) or measured <= 0:
        print("throughput-gate: FAIL — measurement must be finite and positive")
        return 1
    print(f"throughput-gate: measured python_complex throughput = {measured:.3f} MB/s")

    baseline = _load_baseline(baseline_path)

    if baseline is None:
        if require_baseline:
            print("throughput-gate: FAIL — required baseline is missing or invalid")
            return 1
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
    if not math.isfinite(median_baseline) or median_baseline <= 0:
        print("throughput-gate: FAIL — baseline median must be finite and positive")
        return 1
    threshold = median_baseline * REGRESSION_THRESHOLD

    print(
        f"throughput-gate: baseline median = {median_baseline:.3f} MB/s "
        f"(threshold = {threshold:.3f} MB/s, history n={len(history)})"
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


_REFERENCE_HARNESS = """
import importlib.metadata
import json
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from omnichunk import Chunker, __version__
text = Path(sys.argv[2]).read_text(encoding='utf-8')
raw = text.encode('utf-8')
chunker = Chunker(max_chunk_size=512, min_chunk_size=128, size_unit='chars',
                  context_mode='none', overlap=None, overlap_lines=0, nws_backend='python')
def run():
    return chunker.chunk('benchmark.py', text)
run()
samples = []
for _ in range(7):
    started = time.perf_counter()
    for _ in range(20):
        chunks = run()
    samples.append(len(raw) * 20 / (time.perf_counter() - started))
dependencies = {}
for name in ('numpy', 'tree-sitter', 'tree-sitter-python', 'tiktoken'):
    try:
        dependencies[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        dependencies[name] = None
print(json.dumps({'version': __version__, 'bytes_per_second': statistics.median(samples),
    'samples': samples, 'chunks': len(chunks), 'dependencies': dependencies,
    'max_chars': max((len(c.contextualized_text) for c in chunks), default=0),
    'reconstruction': ''.join(c.text for c in chunks) == text}))
"""


def _measure_source(source_root: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            _REFERENCE_HARNESS,
            str(source_root),
            str(ROOT / BASELINE_FIXTURE),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=source_root.parent,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    if not isinstance(payload, dict):
        raise ValueError("Benchmark harness did not produce a measurement object")
    return payload


def reference_comparison_status(baseline: dict[str, Any], candidate: dict[str, Any]) -> str:
    """Only comparable, measured, source-preserving outputs can pass."""
    for row in (baseline, candidate):
        rate = float(row.get("bytes_per_second", 0))
        if not math.isfinite(rate) or rate <= 0:
            return "invalid_measurement"
        if not row.get("reconstruction") or not 0 < row.get("max_chars", 0) <= 512:
            return "invalid_output"
    if baseline.get("dependencies") != candidate.get("dependencies"):
        return "different_dependencies"
    if candidate["bytes_per_second"] < baseline["bytes_per_second"] * REGRESSION_THRESHOLD:
        return "regression"
    return "passed"


def validate_transition_manifest(
    manifest: dict[str, Any],
    report: dict[str, Any],
    release_tag: str | None,
) -> None:
    """Allow one explicit old-contract transition, without asserting speed parity."""
    if not release_tag or not re.fullmatch(r"v?2\.\d+\.\d+(?:(?:a|b|rc)\d+)?", release_tag):
        raise ValueError("Transition baseline is restricted to explicitly tagged 2.x releases")
    if manifest.get("schema_version") != 1 or not str(manifest.get("rationale", "")).strip():
        raise ValueError("Transition manifest requires a version and explicit rationale")
    for key in (
        "baseline_revision",
        "candidate_source_sha256",
        "project_config_sha256",
        "fixture_sha256",
        "harness_sha256",
        "settings",
    ):
        if manifest.get(key) != report.get(key):
            raise ValueError(f"Transition manifest no longer matches {key}; review and regenerate")
    if report["status"] != "invalid_output":
        raise ValueError("Transition exception applies only to the recorded invalid old contract")
    if reference_comparison_status(report["candidate"], report["candidate"]) != "passed":
        raise ValueError("Candidate must satisfy the new contract before establishing a baseline")
    if reference_comparison_status(report["baseline"], report["baseline"]) != "invalid_output":
        raise ValueError("A valid prior baseline must use the ordinary regression gate")


def run_reference_gate(
    reference: str,
    *,
    report_path: Path | None = None,
    transition_manifest: Path | None = None,
    release_tag: str | None = None,
    record_transition: Path | None = None,
    rationale: str | None = None,
) -> int:
    """Compare a Git revision and current source with one harness on this runner.

    Git archive is read-only: no checkout, branch or worktree is changed. The
    same fixture, interpreter and dependency environment are used for both runs.
    The archived revision is repository code and is executed by the harness.
    """
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", f"{reference}^{{commit}}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        archive_bytes = subprocess.run(
            ["git", "archive", "--format=tar", revision, "src/omnichunk"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        with tempfile.TemporaryDirectory(prefix="omnichunk-baseline-") as temporary:
            directory = Path(temporary).resolve()
            with tarfile.open(fileobj=BytesIO(archive_bytes)) as archive:
                for member in archive.getmembers():
                    target = directory / member.name
                    if not target.resolve().is_relative_to(directory) or not (
                        member.isdir() or member.isfile()
                    ):
                        raise ValueError(f"Unsupported archived source entry: {member.name}")
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        content = archive.extractfile(member)
                        if content is None:
                            raise ValueError(f"Cannot read archived source: {member.name}")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content.read())
            baseline = _measure_source(directory / "src")
            candidate = _measure_source(ROOT / "src")
        status = reference_comparison_status(baseline, candidate)
        source_hash = hashlib.sha256()
        for path in sorted((ROOT / "src/omnichunk").rglob("*.py")):
            if path.name == "_version.py":
                continue  # Version-only bumps do not alter chunking behavior.
            source_hash.update(path.relative_to(ROOT).as_posix().encode())
            source_hash.update(path.read_bytes())
        report = {
            "schema_version": 2,
            "status": status,
            "baseline_revision": revision,
            "candidate_source_sha256": source_hash.hexdigest(),
            "project_config_sha256": hashlib.sha256(
                (ROOT / "pyproject.toml").read_bytes()
            ).hexdigest(),
            "fixture": BASELINE_FIXTURE,
            "fixture_sha256": hashlib.sha256((ROOT / BASELINE_FIXTURE).read_bytes()).hexdigest(),
            "harness_sha256": hashlib.sha256(_REFERENCE_HARNESS.encode()).hexdigest(),
            "python": sys.version,
            "platform": platform.platform(),
            "same_runner": True,
            "settings": {
                "size_unit": "chars",
                "max_size": 512,
                "context": "none",
                "overlap": 0,
                "samples": 7,
                "iterations_per_sample": 20,
            },
            "minimum_throughput_ratio": REGRESSION_THRESHOLD,
            "baseline": baseline,
            "candidate": candidate,
        }
        if record_transition is not None:
            if not rationale or not rationale.strip():
                raise ValueError("Recording a transition requires --transition-rationale")
            if (
                status != "invalid_output"
                or reference_comparison_status(candidate, candidate) != "passed"
            ):
                raise ValueError(
                    "Transition requires invalid old output and valid candidate output"
                )
            manifest = {
                key: report[key]
                for key in (
                    "baseline_revision",
                    "candidate_source_sha256",
                    "project_config_sha256",
                    "fixture_sha256",
                    "harness_sha256",
                    "settings",
                )
            }
            manifest.update(
                {
                    "schema_version": 1,
                    "rationale": rationale,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "contract": "canonical-source-exact-character-budget-v2",
                    "speed_parity_claimed": False,
                    "measurement": report,
                }
            )
            record_transition.parent.mkdir(parents=True, exist_ok=True)
            record_transition.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
            report["status"] = "transition_manifest_recorded"
        elif status == "invalid_output" and transition_manifest is not None:
            manifest = json.loads(transition_manifest.read_text())
            if manifest.get("baseline_revision") == revision:
                validate_transition_manifest(manifest, report, release_tag)
                report["legacy_comparison_status"] = status
                report["status"] = "transition_baseline_established"
                report["transition_rationale"] = manifest["rationale"]
                report["speed_parity_claimed"] = False
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps(report, sort_keys=True, allow_nan=False))
        return (
            0
            if report["status"]
            in (
                "passed",
                "transition_manifest_recorded",
                "transition_baseline_established",
            )
            else 1
        )
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(f"reference-gate: FAIL — cannot establish comparable baseline: {exc}")
        return 1


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
    compare_ref = _flag_value("--compare-ref")
    require_baseline = "--require-baseline" in sys.argv
    if require_baseline and not compare_ref:
        print("reference-gate: FAIL — release validation requires --compare-ref REF")
        return 1
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
        or compare_ref is not None
    ):
        print(
            "Benchmark scripts are present. Use --run, --run-compare, --run-compare-extra, "
            "--run-quality, --run-large-corpus, --run-profile, --run-regression-gate "
            "[--update-baseline], or --html-report PATH."
        )
        return 0

    exit_code = 0
    if compare_ref is not None:
        report = _flag_value("--comparison-report")
        manifest = _flag_value("--transition-manifest")
        record = _flag_value("--record-transition-baseline")
        exit_code = max(
            exit_code,
            run_reference_gate(
                compare_ref,
                report_path=Path(report) if report else None,
                transition_manifest=Path(manifest) if manifest else None,
                release_tag=_flag_value("--release-tag"),
                record_transition=Path(record) if record else None,
                rationale=_flag_value("--transition-rationale"),
            ),
        )

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

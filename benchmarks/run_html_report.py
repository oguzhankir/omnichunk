# ruff: noqa: E402
"""
Generate a self-contained HTML benchmark dashboard.

Usage:
    python benchmarks/run_html_report.py
    python benchmarks/run_html_report.py --output reports/benchmark.html
    python benchmarks/run_html_report.py --scenarios python_complex markdown_doc
    python benchmarks/run_html_report.py --repeat 5

The HTML file is self-contained except for Chart.js loaded from cdnjs.cloudflare.com.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import webbrowser
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BENCH_DIR = Path(__file__).resolve().parent
for _p in (SRC, BENCH_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from run_benchmarks import SCENARIOS, Scenario  # noqa: E402
from run_quality_report import QualityRow, evaluate_scenario  # noqa: E402

from omnichunk import Chunker  # noqa: E402
from omnichunk import __version__ as OMNICHUNK_VERSION  # noqa: E402
from omnichunk.sizing.nws import get_nws_backend_status  # noqa: E402

CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"


def _select_scenarios(names: list[str] | None) -> list[Scenario]:
    if not names:
        return list(SCENARIOS)
    by_name = {s.name: s for s in SCENARIOS}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise SystemExit(f"Unknown scenario(s): {', '.join(missing)}")
    return [by_name[n] for n in names]


def _throughput_seconds(chunker: Chunker, scenario: Scenario) -> tuple[int, int, float]:
    text = scenario.path.read_text(encoding="utf-8")
    data_bytes = len(text.encode("utf-8"))
    started = perf_counter()
    chunks = chunker.chunk(
        str(scenario.path),
        text,
        max_chunk_size=scenario.max_chunk_size,
        min_chunk_size=scenario.min_chunk_size,
        size_unit=scenario.size_unit,
    )
    elapsed = perf_counter() - started
    return data_bytes, len(chunks), elapsed


def _median_throughput_row(
    chunker: Chunker, scenario: Scenario, repeat: int
) -> tuple[str, int, int, float, float]:
    durations: list[float] = []
    last_bytes = 0
    last_chunks = 0
    for _ in range(max(1, repeat)):
        data_bytes, nchunks, elapsed = _throughput_seconds(chunker, scenario)
        durations.append(elapsed)
        last_bytes, last_chunks = data_bytes, nchunks
    med = float(statistics.median(durations))
    mbps = 0.0
    if med > 0:
        mbps = (last_bytes / (1024 * 1024)) / med
    return scenario.name, last_bytes, last_chunks, med, mbps


def _quality_rows(chunker: Chunker, scenarios: list[Scenario]) -> list[QualityRow]:
    return [evaluate_scenario(chunker, s) for s in scenarios]


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(
    *,
    throughput: list[tuple[str, int, int, float, float]],
    quality: list[QualityRow],
    raw_payload: dict[str, Any],
) -> str:
    labels = json.dumps([r[0] for r in throughput])
    mbps_vals = json.dumps([round(r[4], 6) for r in throughput])

    def _badge(ok: bool) -> str:
        if ok:
            return '<span class="pass">PASS</span>'
        return '<span class="fail">FAIL</span>'

    rows_t = []
    for name, nbytes, nchunks, secs, mbps in throughput:
        rows_t.append(
            "<tr>"
            f"<td>{_escape_html(name)}</td>"
            f"<td>{nbytes}</td>"
            f"<td>{nchunks}</td>"
            f"<td>{secs:.6f}</td>"
            f"<td>{mbps:.3f}</td>"
            "</tr>"
        )

    rows_q = []
    for row in quality:
        ok = (
            row.reconstruction_ok
            and row.contiguous_ok
            and row.non_empty_ok
            and row.deterministic_ok
        )
        rows_q.append(
            "<tr>"
            f"<td>{_escape_html(row.scenario)}</td>"
            f"<td>{_badge(row.reconstruction_ok)}</td>"
            f"<td>{_badge(row.contiguous_ok)}</td>"
            f"<td>{_badge(row.non_empty_ok)}</td>"
            f"<td>{_badge(row.deterministic_ok)}</td>"
            f"<td>{_badge(ok)}</td>"
            "</tr>"
        )

    raw_json = json.dumps(raw_payload, indent=2, ensure_ascii=False)
    meta_ts = _escape_html(raw_payload["timestamp"])
    meta_ver = _escape_html(str(raw_payload["version"]))
    meta_nws = _escape_html(json.dumps(raw_payload["nws_backend"]))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>omnichunk Benchmark Report</title>
  <script src="{CHART_JS}"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.5rem; }}
    table {{ border-collapse: collapse; margin: 1rem 0; }}
    th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.6rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
    .pass {{ color: #0a0; font-weight: 600; }}
    .fail {{ color: #c00; font-weight: 600; }}
    pre {{ background: #f8f8f8; padding: 1rem; overflow: auto; max-height: 28rem; }}
    canvas {{ max-width: 900px; }}
  </style>
</head>
<body>
  <h1>omnichunk Benchmark Report</h1>
  <p>Generated: {meta_ts} | Version: {meta_ver} | NWS backend: {meta_nws}</p>

  <h2>Throughput</h2>
  <table>
    <thead><tr><th>scenario</th><th>bytes</th><th>chunks</th><th>median_seconds</th><th>MBps</th></tr></thead>
    <tbody>{"".join(rows_t)}</tbody>
  </table>
  <canvas id="throughputChart" height="120"></canvas>

  <h2>Quality</h2>
  <table>
    <thead><tr><th>scenario</th><th>reconstruction</th><th>contiguous</th><th>non_empty</th><th>deterministic</th><th>status</th></tr></thead>
    <tbody>{"".join(rows_q)}</tbody>
  </table>

  <h2>Raw Data</h2>
  <pre id="omnichunk-raw-json">{_escape_html(raw_json)}</pre>

  <script>
    const labels = {labels};
    const mbps = {mbps_vals};
    const ctx = document.getElementById('throughputChart');
    new Chart(ctx, {{
      type: 'bar',
      data: {{
        labels: labels,
        datasets: [{{
          label: 'MB/s',
          data: mbps,
          backgroundColor: 'rgba(54, 162, 235, 0.6)',
        }}],
      }},
      options: {{
        responsive: true,
        scales: {{ y: {{ beginAtZero: true }} }},
      }},
    }});
  </script>
</body>
</html>
"""


def run_report(
    *,
    output_path: Path,
    repeat: int,
    scenario_names: list[str] | None,
    open_browser: bool,
) -> int:
    scenarios = _select_scenarios(scenario_names)
    chunker = Chunker()

    throughput = [_median_throughput_row(chunker, s, repeat) for s in scenarios]
    quality = _quality_rows(chunker, scenarios)

    nws = get_nws_backend_status(backend=None)
    raw_payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": OMNICHUNK_VERSION,
        "nws_backend": dict(nws),
        "repeat": repeat,
        "throughput": [
            {
                "scenario": r[0],
                "bytes": r[1],
                "chunks": r[2],
                "median_seconds": r[3],
                "mbps": r[4],
            }
            for r in throughput
        ],
        "quality": [asdict(q) for q in quality],
    }

    html = build_html(throughput=throughput, quality=quality, raw_payload=raw_payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(str(output_path.resolve()))

    if open_browser:
        webbrowser.open(output_path.resolve().as_uri())

    all_ok = all(
        q.reconstruction_ok and q.contiguous_ok and q.non_empty_ok and q.deterministic_ok
        for q in quality
    )
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate HTML benchmark dashboard.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output HTML path (default: reports/benchmark_<timestamp>.html)",
    )
    parser.add_argument("--repeat", type=int, default=3, help="Runs per scenario (median time)")
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=None,
        help="Scenario names (default: all)",
    )
    parser.add_argument("--open", action="store_true", help="Open report in default browser")
    args = parser.parse_args(argv)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = args.output or (ROOT / "reports" / f"benchmark_{ts}.html")
    return run_report(
        output_path=out,
        repeat=args.repeat,
        scenario_names=args.scenarios,
        open_browser=args.open,
    )


if __name__ == "__main__":
    raise SystemExit(main())

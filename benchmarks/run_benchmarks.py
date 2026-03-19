# ruff: noqa: E402
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BENCH_DIR = Path(__file__).resolve().parent
for _p in (SRC, BENCH_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from comparison_format import format_scenario_benchmark_table

from omnichunk import Chunker


@dataclass(frozen=True)
class Scenario:
    name: str
    path: Path
    max_chunk_size: int
    min_chunk_size: int
    size_unit: str = "chars"


FIXTURES = ROOT / "tests" / "fixtures"

SCENARIOS: list[Scenario] = [
    Scenario(
        "python_complex",
        FIXTURES / "python_complex.py",
        max_chunk_size=260,
        min_chunk_size=80,
    ),
    Scenario(
        "markdown_doc",
        FIXTURES / "markdown_doc.md",
        max_chunk_size=300,
        min_chunk_size=90,
    ),
    Scenario(
        "html_page",
        FIXTURES / "html_page.html",
        max_chunk_size=300,
        min_chunk_size=80,
    ),
    Scenario(
        "sample_json",
        FIXTURES / "sample.json",
        max_chunk_size=200,
        min_chunk_size=60,
    ),
    # Synthetic large Python: `python_complex.py` repeated 50× (see workloads mega-python).
    Scenario(
        "mega_python_50x",
        FIXTURES / "mega_python_50x.py",
        max_chunk_size=512,
        min_chunk_size=128,
        size_unit="chars",
    ),
]


def run() -> int:
    chunker = Chunker()
    print("Scenario,Bytes,Chunks,Seconds,MBps")

    total_bytes = 0
    total_seconds = 0.0
    summary_rows: list[tuple[str, int, int, float, float]] = []

    for scenario in SCENARIOS:
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

        mbps = 0.0
        if elapsed > 0:
            mbps = (data_bytes / (1024 * 1024)) / elapsed

        total_bytes += data_bytes
        total_seconds += elapsed
        nchunks = len(chunks)
        summary_rows.append((scenario.name, data_bytes, nchunks, elapsed, mbps))

        print(f"{scenario.name},{data_bytes},{nchunks},{elapsed:.6f},{mbps:.3f}")

    total_mbps = 0.0
    if total_seconds > 0:
        total_mbps = (total_bytes / (1024 * 1024)) / total_seconds

    print(f"TOTAL,{total_bytes},-,{total_seconds:.6f},{total_mbps:.3f}")

    print()
    print(format_scenario_benchmark_table(summary_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

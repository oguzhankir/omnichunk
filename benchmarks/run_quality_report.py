from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from omnichunk import Chunk, Chunker

from run_benchmarks import SCENARIOS, Scenario


@dataclass(frozen=True)
class QualityRow:
    scenario: str
    chunk_count: int
    reconstruction_ok: bool
    contiguous_ok: bool
    non_empty_ok: bool
    deterministic_ok: bool


def _is_contiguous_non_overlapping(chunks: list[Chunk]) -> bool:
    if not chunks:
        return True

    ordered = sorted(chunks, key=lambda c: c.byte_range.start)
    cursor = ordered[0].byte_range.start
    for chunk in ordered:
        start = chunk.byte_range.start
        end = chunk.byte_range.end
        if end < start:
            return False
        if start != cursor:
            return False
        cursor = end
    return True


def _is_deterministic(left: list[Chunk], right: list[Chunk]) -> bool:
    if len(left) != len(right):
        return False

    for lchunk, rchunk in zip(left, right):
        if lchunk.text != rchunk.text:
            return False
        if lchunk.contextualized_text != rchunk.contextualized_text:
            return False
        if lchunk.byte_range != rchunk.byte_range:
            return False
        if lchunk.line_range != rchunk.line_range:
            return False
        if lchunk.context != rchunk.context:
            return False

    return True


def evaluate_scenario(chunker: Chunker, scenario: Scenario) -> QualityRow:
    text = scenario.path.read_text(encoding="utf-8")
    chunks = chunker.chunk(
        str(scenario.path),
        text,
        max_chunk_size=scenario.max_chunk_size,
        min_chunk_size=scenario.min_chunk_size,
        size_unit=scenario.size_unit,
    )
    repeated = chunker.chunk(
        str(scenario.path),
        text,
        max_chunk_size=scenario.max_chunk_size,
        min_chunk_size=scenario.min_chunk_size,
        size_unit=scenario.size_unit,
    )

    reconstruction_ok = "".join(c.text for c in chunks) == text
    contiguous_ok = _is_contiguous_non_overlapping(chunks)
    non_empty_ok = all(c.text.strip() for c in chunks)
    deterministic_ok = _is_deterministic(chunks, repeated)

    return QualityRow(
        scenario=scenario.name,
        chunk_count=len(chunks),
        reconstruction_ok=reconstruction_ok,
        contiguous_ok=contiguous_ok,
        non_empty_ok=non_empty_ok,
        deterministic_ok=deterministic_ok,
    )


def run() -> int:
    chunker = Chunker()
    print("Scenario,Chunks,Reconstruction,Contiguous,NonEmpty,Deterministic")

    rows: list[QualityRow] = [evaluate_scenario(chunker, scenario) for scenario in SCENARIOS]
    for row in rows:
        print(
            f"{row.scenario},{row.chunk_count},"
            f"{str(row.reconstruction_ok).lower()},"
            f"{str(row.contiguous_ok).lower()},"
            f"{str(row.non_empty_ok).lower()},"
            f"{str(row.deterministic_ok).lower()}"
        )

    all_ok = all(
        row.reconstruction_ok and row.contiguous_ok and row.non_empty_ok and row.deterministic_ok
        for row in rows
    )
    print(f"TOTAL,{len(rows)},status={'ok' if all_ok else 'fail'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(run())

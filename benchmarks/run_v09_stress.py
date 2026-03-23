# ruff: noqa: E402
"""Stress/latency harness for v0.9 deduplication and evaluation (no pytest-benchmark required).

Usage (from repo root)::

    python benchmarks/run_v09_stress.py
    python benchmarks/run_v09_stress.py --dedup-n 8000 --eval-n 1200 --threshold 0.85
    python benchmarks/run_v09_stress.py --with-ipynb

Exits 0 after printing a CSV-style table to stdout.

Note: default dedup text varies ``# id=`` per chunk — simhash finds many near-dups; minhash
often finds none (see benchmarks/README “Interpreting dedup rows”).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from omnichunk import Chunker, dedup_chunks, evaluate_chunks
from omnichunk.types import ByteRange, Chunk, ChunkContext, ContentType, LineRange


def _nws_count(text: str) -> int:
    return sum(1 for c in text if not c.isspace())


def _synthetic_chunk(index: int, *, variant: str) -> Chunk:
    """Minimal valid Chunk for dedup/eval timing (ASCII-only, byte_range matches text)."""
    if variant == "dedup":
        # Many near-duplicates: same body, different suffix → stresses simhash/minhash
        body = "def helper():\n    return 42\n"
        text = f"{body}# id={index}\n"
    else:
        # Multi-sentence prose for coherence / boundary metrics
        text = (
            f"Alpha sentence one. Beta sentence two. Gamma sentence three. "
            f"Delta sentence four. Echo sentence five. Chunk index {index}.\n"
        )
    raw = text.encode("utf-8")
    line_end = max(0, text.count("\n") - 1)
    ctx = ChunkContext(
        filepath=f"synthetic/{index}.txt",
        language="plaintext",
        content_type=ContentType.PROSE,
    )
    return Chunk(
        text=text,
        contextualized_text=text,
        byte_range=ByteRange(start=0, end=len(raw)),
        line_range=LineRange(start=0, end=line_end),
        index=index,
        total_chunks=-1,
        context=ctx,
        token_count=max(1, len(text) // 4),
        char_count=len(text),
        nws_count=_nws_count(text),
    )


def _build_dedup_corpus(n: int) -> list[Chunk]:
    return [_synthetic_chunk(i, variant="dedup") for i in range(n)]


def _build_eval_corpus(n: int) -> list[Chunk]:
    return [_synthetic_chunk(i, variant="eval") for i in range(n)]


def _run_dedup(chunks: list[Chunk], threshold: float) -> None:
    for method in ("exact", "simhash", "minhash"):
        t0 = perf_counter()
        unique, dup_map = dedup_chunks(chunks, method=method, threshold=threshold)
        elapsed = perf_counter() - t0
        print(
            f"dedup,{method},{len(chunks)},{len(unique)},{len(dup_map)},{elapsed:.6f}",
            flush=True,
        )


def _run_eval(chunks: list[Chunk], source: str | None) -> None:
    t0 = perf_counter()
    report = evaluate_chunks(chunks, source=source, metrics="all")
    elapsed = perf_counter() - t0
    agg = report.aggregate
    keys = ("reconstruction", "density", "coherence", "boundary_quality", "coverage")
    payload = {k: agg.get(k) for k in keys}
    print(
        f"eval,all_metrics,{len(chunks)},-,-,{elapsed:.6f}",
        flush=True,
    )
    print("eval_aggregate," + json.dumps(payload, separators=(",", ":")), flush=True)


def _run_ipynb_chunk(fixture: Path) -> None:
    chunker = Chunker(max_chunk_size=512, size_unit="chars")
    t0 = perf_counter()
    chunks = chunker.chunk_file(str(fixture))
    elapsed = perf_counter() - t0
    raw = len(fixture.read_bytes())
    print(
        f"chunk_file,ipynb,{raw},{len(chunks)},-,{elapsed:.6f}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="v0.9 dedup + eval stress timings")
    parser.add_argument(
        "--dedup-n",
        type=int,
        default=5000,
        help="Number of synthetic chunks for dedup_* timings",
    )
    parser.add_argument(
        "--eval-n",
        type=int,
        default=800,
        help="Number of synthetic chunks for evaluate_chunks timing",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="dedup simhash/minhash threshold",
    )
    parser.add_argument(
        "--with-ipynb",
        action="store_true",
        help="Also time Chunker.chunk_file on tests/fixtures/sample_v09.ipynb",
    )
    args = parser.parse_args()

    if args.dedup_n < 1 or args.eval_n < 1:
        print("dedup-n and eval-n must be >= 1", file=sys.stderr)
        return 2

    print(
        "phase,method,n_input,n_unique,n_dups,seconds",
        flush=True,
    )

    dedup_chunks_list = _build_dedup_corpus(args.dedup_n)
    _run_dedup(dedup_chunks_list, threshold=args.threshold)

    eval_chunks_list = _build_eval_corpus(args.eval_n)
    # Single synthetic "source" string: concatenation of chunk texts (reconstruction-friendly)
    source = "".join(c.text for c in eval_chunks_list)
    _run_eval(eval_chunks_list, source=source)

    if args.with_ipynb:
        fixture = ROOT / "tests" / "fixtures" / "sample_v09.ipynb"
        if not fixture.exists():
            print(f"missing_fixture,{fixture}", file=sys.stderr)
            return 1
        _run_ipynb_chunk(fixture)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from omnichunk.semantic.sentences import split_sentences
from omnichunk.types import Chunk

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class ChunkEvalScores:
    index: int
    reconstruction: float | None
    density: float | None
    coherence: float | None
    boundary_quality: float | None
    coverage: float | None


@dataclass(frozen=True)
class EvalReport:
    per_chunk: tuple[ChunkEvalScores, ...]
    aggregate: dict[str, float | None]


def evaluate_chunks(
    chunks: Sequence[Chunk],
    source: str | None = None,
    *,
    metrics: Sequence[str] | Literal["all"] = "all",
) -> EvalReport:
    """Offline metrics for chunk quality (no embeddings)."""
    if metrics == "all":
        want = frozenset({"reconstruction", "density", "coherence", "boundary_quality", "coverage"})
    else:
        want = frozenset(metrics)

    allowed = {"reconstruction", "density", "coherence", "boundary_quality", "coverage"}
    if want - allowed:
        raise ValueError(f"Unknown evaluation metrics: {sorted(want - allowed)}")
    raw_source = source.encode("utf-8") if source is not None else None
    n = len(chunks)
    per: list[ChunkEvalScores] = []

    for i, ch in enumerate(chunks):
        rec = (
            _metric_reconstruction(ch, source, raw_source=raw_source)
            if "reconstruction" in want
            else None
        )
        dens = _metric_density(ch) if "density" in want else None
        coh = _metric_coherence(ch) if "coherence" in want else None
        bq = _metric_boundary(chunks, i) if "boundary_quality" in want and n > 1 else None
        cov = (
            _metric_coverage_chunk(chunks, i, source, raw_source=raw_source)
            if "coverage" in want
            else None
        )
        per.append(
            ChunkEvalScores(
                index=ch.index,
                reconstruction=rec,
                density=dens,
                coherence=coh,
                boundary_quality=bq,
                coverage=cov,
            )
        )

    agg: dict[str, float | None] = {}
    for name in ("reconstruction", "density", "coherence", "boundary_quality", "coverage"):
        if name not in want:
            agg[name] = None
            continue
        vals = [getattr(row, name) for row in per]
        nums = [v for v in vals if v is not None]
        agg[name] = float(sum(nums) / len(nums)) if nums else None

    if "coverage" in want and raw_source is not None:
        intervals = sorted(
            (c.byte_range.start, c.byte_range.end)
            for c in chunks
            if _metric_reconstruction(c, source, raw_source=raw_source) == 1.0
        )
        covered, end = 0, 0
        for start, finish in intervals:
            covered += max(0, finish - max(start, end))
            end = max(end, finish)
        agg["coverage"] = covered / len(raw_source) if raw_source else 1.0
    return EvalReport(per_chunk=tuple(per), aggregate=agg)


def _metric_reconstruction(
    chunk: Chunk, source: str | None, *, raw_source: bytes | None = None
) -> float | None:
    if source is None:
        return None
    raw = raw_source if raw_source is not None else source.encode("utf-8")
    start, end = chunk.byte_range.start, chunk.byte_range.end
    if start < 0 or end > len(raw) or start > end:
        return 0.0
    slice_b = raw[start:end].decode("utf-8", errors="replace")
    return 1.0 if slice_b == chunk.text else 0.0


def _metric_density(chunk: Chunk) -> float | None:
    chars = max(1, chunk.char_count)
    return float(chunk.nws_count) / float(chars)


def _metric_coherence(chunk: Chunk) -> float | None:
    import numpy as np

    from omnichunk.semantic.tfidf import build_tfidf_matrix

    sents = [t[0] for t in split_sentences(chunk.text) if t[0].strip()]
    if len(sents) < 2:
        return 1.0
    mat = build_tfidf_matrix(sents, max_vocab=2048)
    if mat.shape[0] < 2 or mat.shape[1] == 0:
        return 0.0
    sims: list[float] = []
    for a in range(len(sents) - 1):
        v0, v1 = mat[a], mat[a + 1]
        d = float(np.linalg.norm(v0) * np.linalg.norm(v1))
        sims.append(float(np.dot(v0, v1) / d) if d > 0 else 0.0)
    return float(sum(sims) / len(sims)) if sims else 0.0


def _metric_boundary(chunks: Sequence[Chunk], index: int) -> float | None:
    import numpy as np

    from omnichunk.semantic.tfidf import build_tfidf_matrix

    if index <= 0:
        return None
    prev_t = chunks[index - 1].text
    cur_t = chunks[index].text
    tail = [t[0] for t in split_sentences(prev_t) if t[0].strip()]
    head = [t[0] for t in split_sentences(cur_t) if t[0].strip()]
    if not tail or not head:
        return None
    before = " ".join(tail[-2:]) if len(tail) >= 2 else tail[-1]
    after = " ".join(head[:2]) if len(head) >= 2 else head[0]
    mat = build_tfidf_matrix([before, after], max_vocab=2048)
    if mat.shape[1] == 0:
        return None
    v0, v1 = mat[0], mat[1]
    d = float(np.linalg.norm(v0) * np.linalg.norm(v1))
    sim = float(np.dot(v0, v1) / d) if d > 0 else 0.0
    return 1.0 - sim


def _metric_coverage_chunk(
    chunks: Sequence[Chunk],
    index: int,
    source: str | None,
    *,
    raw_source: bytes | None = None,
) -> float | None:
    if source is None:
        return None
    raw = raw_source if raw_source is not None else source.encode("utf-8")
    chunk = chunks[index]
    if _metric_reconstruction(chunk, source, raw_source=raw) != 1.0:
        return 0.0
    return (chunk.byte_range.end - chunk.byte_range.start) / len(raw) if raw else 1.0


def _token_set(text: str) -> set[str]:
    return set(t.lower() for t in _TOKEN.findall(text))


def eval_report_to_dict(report: EvalReport) -> dict[str, Any]:
    return {
        "aggregate": dict(report.aggregate),
        "per_chunk": [
            {
                "index": row.index,
                "reconstruction": row.reconstruction,
                "density": row.density,
                "coherence": row.coherence,
                "boundary_quality": row.boundary_quality,
                "coverage": row.coverage,
            }
            for row in report.per_chunk
        ],
    }

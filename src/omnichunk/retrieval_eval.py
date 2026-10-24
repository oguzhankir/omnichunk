"""Retrieval ranking and source-evidence metrics, independent of a retriever.

Ranking scores compare passage IDs against explicit graded relevance judgments.
Evidence scores compare the union of canonical UTF-8 source byte ranges. Keep
both: a relevant passage can still contain much unrelated text or only part of
the evidence. These metrics do not measure answer correctness.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Real


@dataclass(frozen=True)
class EvidenceSpan:
    """A nonempty half-open UTF-8 byte range in one canonical source revision.

    The caller must use the same canonical text and revision for matching source
    IDs. This value validates coordinates, not the original source bytes.
    """

    source_id: str
    start: int
    end: int

    def __post_init__(self) -> None:
        _validate_id(self.source_id)
        if (
            not isinstance(self.start, int)
            or isinstance(self.start, bool)
            or not isinstance(self.end, int)
            or isinstance(self.end, bool)
            or self.start < 0
            or self.end <= self.start
        ):
            raise ValueError("Evidence spans require integer coordinates with 0 <= start < end")


@dataclass(frozen=True)
class RankingMetrics:
    """Scores at one cutoff; relevant_count counts all positive judgments."""

    recall_at_k: float
    mrr_at_k: float
    ndcg_at_k: float
    k: int
    relevant_count: int
    retrieved_count: int


@dataclass(frozen=True)
class EvidenceMetrics:
    """Source-byte union metrics and their exact integer denominators."""

    precision: float
    recall: float
    iou: float
    retrieved_bytes: int
    relevant_bytes: int
    intersection_bytes: int


def _validate_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Source and passage IDs must be nonempty strings")


def score_ranking(
    retrieved_ids: Sequence[str], relevance: Mapping[str, float], *, k: int = 5
) -> RankingMetrics:
    """Compute Recall@k, reciprocal rank@k and graded nDCG@k.

    Unjudged IDs have relevance zero. Positive judgments define the recall
    denominator; nDCG uses exponential gains (``2**grade - 1``) and an ideal
    ranking from *all* judgments, including missed passages. Grades must be
    finite and nonnegative. Duplicate IDs consume rank slots but receive no
    repeated credit. No positive judgments yields zero for all three scores.
    """
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("k must be a positive integer")
    for passage_id in retrieved_ids:
        _validate_id(passage_id)
    grades: dict[str, float] = {}
    for passage_id, grade in relevance.items():
        _validate_id(passage_id)
        if isinstance(grade, bool) or not isinstance(grade, Real):
            raise ValueError("Relevance grades must be finite nonnegative real numbers")
        try:
            number = float(grade)
        except (OverflowError, ValueError) as exc:
            raise ValueError("Relevance grades must be finite nonnegative real numbers") from exc
        if not math.isfinite(number) or number < 0:
            raise ValueError("Relevance grades must be finite nonnegative real numbers")
        grades[passage_id] = number
    positive = sorted((value for value in grades.values() if value > 0), reverse=True)
    maximum = positive[0] if positive else 0.0

    def gain(grade: float) -> float:
        # Scaling by 2**(-maximum) cancels between DCG and IDCG, avoiding
        # overflow for large valid grades. expm1 preserves tiny positive grades.
        return -math.expm1(-grade * math.log(2)) * math.pow(2.0, grade - maximum)

    seen: set[str] = set()
    hits, reciprocal_rank, dcg = 0, 0.0, 0.0
    for rank, passage_id in enumerate(retrieved_ids[:k], start=1):
        if passage_id in seen:
            continue
        seen.add(passage_id)
        grade = grades.get(passage_id, 0.0)
        if grade > 0:
            hits += 1
            if reciprocal_rank == 0:
                reciprocal_rank = 1.0 / rank
            dcg += gain(grade) / math.log2(rank + 1)
    ideal = sum(gain(grade) / math.log2(rank + 1) for rank, grade in enumerate(positive[:k], 1))
    return RankingMetrics(
        recall_at_k=hits / len(positive) if positive else 0.0,
        mrr_at_k=reciprocal_rank,
        ndcg_at_k=dcg / ideal if ideal else 0.0,
        k=k,
        relevant_count=len(positive),
        retrieved_count=min(k, len(retrieved_ids)),
    )


def _union(spans: Sequence[EvidenceSpan]) -> dict[str, list[tuple[int, int]]]:
    grouped: dict[str, list[tuple[int, int]]] = {}
    for span in spans:
        if not isinstance(span, EvidenceSpan):
            raise ValueError("Evidence collections must contain EvidenceSpan values")
        grouped.setdefault(span.source_id, []).append((span.start, span.end))
    for source_id, intervals in grouped.items():
        merged: list[tuple[int, int]] = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        grouped[source_id] = merged
    return grouped


def score_evidence(
    retrieved: Sequence[EvidenceSpan], relevant: Sequence[EvidenceSpan]
) -> EvidenceMetrics:
    """Measure precision, recall and IoU of source-byte unions per document.

    Repeated/overlapping ranges count once; identically numbered ranges in
    different sources never match. Both sets empty gives 1 for all metrics.
    If only one set is empty, all metrics are 0. These are byte-weighted scores,
    so non-ASCII characters contribute their full UTF-8 width.
    """
    predicted, expected = _union(retrieved), _union(relevant)
    predicted_size = sum(end - start for spans in predicted.values() for start, end in spans)
    expected_size = sum(end - start for spans in expected.values() for start, end in spans)
    intersection = 0
    for source_id, spans in predicted.items():
        gold = expected.get(source_id, [])
        cursor = 0
        for start, end in spans:
            while cursor < len(gold) and gold[cursor][1] <= start:
                cursor += 1
            index = cursor
            while index < len(gold) and gold[index][0] < end:
                gold_start, gold_end = gold[index]
                intersection += max(0, min(end, gold_end) - max(start, gold_start))
                index += 1
    union_size = predicted_size + expected_size - intersection
    both_empty = predicted_size == expected_size == 0
    return EvidenceMetrics(
        precision=intersection / predicted_size if predicted_size else float(both_empty),
        recall=intersection / expected_size if expected_size else float(both_empty),
        iou=intersection / union_size if union_size else 1.0,
        retrieved_bytes=predicted_size,
        relevant_bytes=expected_size,
        intersection_bytes=intersection,
    )

"""
Token budget optimizer for RAG context window management.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from omnichunk.types import Chunk


@dataclass(frozen=True)
class BudgetResult:
    """Result of token budget optimization."""

    selected: list[Chunk]
    total_tokens: int
    dropped: list[Chunk]
    budget: int
    strategy: str


class TokenBudgetOptimizer:
    """Select the best subset of chunks that fits within a token budget."""

    def __init__(
        self,
        budget: int,
        *,
        strategy: str = "greedy",
        preserve_order: bool = True,
        deduplicate_overlap: bool = False,
        overlap_threshold: float = 0.85,
        size_unit: str = "tokens",
    ) -> None:
        if budget <= 0:
            raise ValueError("budget must be > 0")
        if strategy not in ("greedy", "dp"):
            raise ValueError("strategy must be 'greedy' or 'dp'")
        if not (0 < overlap_threshold <= 1):
            raise ValueError("overlap_threshold must be in (0, 1]")
        self.budget = budget
        self.strategy = strategy
        self.preserve_order = preserve_order
        self.deduplicate_overlap = deduplicate_overlap
        self.overlap_threshold = overlap_threshold
        self.size_unit = size_unit

    def select(
        self,
        chunks: Sequence[Chunk],
        *,
        scores: Sequence[float] | None = None,
    ) -> BudgetResult:
        if not chunks:
            return BudgetResult(
                selected=[],
                total_tokens=0,
                dropped=[],
                budget=self.budget,
                strategy=self.strategy,
            )
        if scores is not None and len(scores) != len(chunks):
            raise ValueError("scores must have same length as chunks")

        effective_scores = list(scores) if scores is not None else [1.0] * len(chunks)

        working: list[Chunk] = list(chunks)
        working_scores: list[float] = list(effective_scores)

        if self.deduplicate_overlap:
            working, working_scores = _deduplicate(
                working, working_scores, self.overlap_threshold
            )

        if self.strategy == "greedy":
            selected_indices = _greedy_select(
                working, working_scores, self.budget, self.size_unit
            )
        else:
            selected_indices = _dp_select(
                working, working_scores, self.budget, self.size_unit
            )

        selected = [working[i] for i in selected_indices]
        if self.preserve_order:
            selected.sort(key=lambda c: c.byte_range.start)

        selected_ids = {id(c) for c in selected}
        dropped = [c for c in chunks if id(c) not in selected_ids]

        total = sum(_chunk_size(c, self.size_unit) for c in selected)

        return BudgetResult(
            selected=selected,
            total_tokens=total,
            dropped=dropped,
            budget=self.budget,
            strategy=self.strategy,
        )


def _chunk_size(chunk: Chunk, size_unit: str) -> int:
    if size_unit == "tokens":
        return max(1, int(chunk.token_count))
    if size_unit == "nws":
        return max(1, int(chunk.nws_count))
    return max(1, int(chunk.char_count))


def _greedy_select(
    chunks: list[Chunk],
    scores: list[float],
    budget: int,
    size_unit: str,
) -> list[int]:
    indexed = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    selected: list[int] = []
    remaining = budget
    for i in indexed:
        size = _chunk_size(chunks[i], size_unit)
        if size <= remaining:
            selected.append(i)
            remaining -= size
    return selected


def _dp_select(
    chunks: list[Chunk],
    scores: list[float],
    budget: int,
    size_unit: str,
) -> list[int]:
    n = len(chunks)
    sizes = [_chunk_size(c, size_unit) for c in chunks]
    if n * budget > 50_000_000:
        return _greedy_select(chunks, scores, budget, size_unit)

    neg = float("-inf")
    dp: list[list[float]] = [[neg] * (budget + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(1, n + 1):
        wi = sizes[i - 1]
        vi = scores[i - 1]
        for w in range(budget + 1):
            best = dp[i - 1][w]
            if w >= wi and dp[i - 1][w - wi] > neg:
                best = max(best, dp[i - 1][w - wi] + vi)
            dp[i][w] = best

    best_w = max(range(budget + 1), key=lambda w: (dp[n][w], -w))
    if dp[n][best_w] <= neg:
        return []

    selected: list[int] = []
    w = best_w
    for i in range(n, 0, -1):
        if dp[i][w] > dp[i - 1][w] + 1e-12:
            selected.append(i - 1)
            w -= sizes[i - 1]

    return selected


def _jaccard_nws(a: str, b: str) -> float:
    tok_a = set(re.findall(r"\S+", a))
    tok_b = set(re.findall(r"\S+", b))
    if not tok_a and not tok_b:
        return 1.0
    if not tok_a or not tok_b:
        return 0.0
    inter = len(tok_a & tok_b)
    union = len(tok_a | tok_b)
    return inter / union if union > 0 else 0.0


def _deduplicate(
    chunks: list[Chunk],
    scores: list[float],
    threshold: float,
) -> tuple[list[Chunk], list[float]]:
    paired = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    kept: list[int] = []
    for i in paired:
        dominated = False
        for j in kept:
            if _jaccard_nws(chunks[i].text, chunks[j].text) >= threshold:
                dominated = True
                break
        if not dominated:
            kept.append(i)

    order = sorted(kept)
    return (
        [chunks[i] for i in order],
        [scores[i] for i in order],
    )

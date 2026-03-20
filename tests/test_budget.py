from __future__ import annotations

import pytest

from omnichunk.budget import BudgetResult, TokenBudgetOptimizer
from omnichunk.types import ByteRange, Chunk, ChunkContext, LineRange


def _make_chunks(texts: list[str], filepath: str = "f.py") -> list[Chunk]:
    chunks = []
    cursor = 0
    for i, text in enumerate(texts):
        end = cursor + len(text.encode("utf-8"))
        chunks.append(
            Chunk(
                text=text,
                contextualized_text=text,
                byte_range=ByteRange(cursor, end),
                line_range=LineRange(i, i),
                index=i,
                total_chunks=len(texts),
                context=ChunkContext(filepath=filepath, language="python"),
                token_count=len(text.split()),
                char_count=len(text),
                nws_count=sum(1 for c in text if not c.isspace()),
            )
        )
        cursor = end
    return chunks


def test_greedy_selects_within_budget() -> None:
    texts = ["hello world " * 10, "foo bar " * 5, "x " * 3]
    chunks = _make_chunks(texts)
    scores = [1.0, 0.9, 0.5]
    opt = TokenBudgetOptimizer(budget=20, strategy="greedy", size_unit="chars")
    result = opt.select(chunks, scores=scores)
    assert isinstance(result, BudgetResult)
    assert result.total_tokens <= 20
    assert result.strategy == "greedy"


def test_dp_selects_within_budget() -> None:
    texts = ["hello world"] * 5
    chunks = _make_chunks(texts)
    scores = [float(i) for i in range(5)]
    opt = TokenBudgetOptimizer(budget=30, strategy="dp", size_unit="chars")
    result = opt.select(chunks, scores=scores)
    assert result.total_tokens <= 30


def test_preserve_order_true() -> None:
    texts = [f"chunk {i} " * 5 for i in range(10)]
    chunks = _make_chunks(texts)
    scores = list(reversed(range(len(chunks))))
    opt = TokenBudgetOptimizer(budget=100, preserve_order=True, size_unit="chars")
    result = opt.select(chunks, scores=scores)
    for left, right in zip(result.selected, result.selected[1:]):
        assert left.byte_range.start <= right.byte_range.start


def test_empty_input() -> None:
    opt = TokenBudgetOptimizer(budget=100)
    result = opt.select([])
    assert result.selected == []
    assert result.total_tokens == 0


def test_added_and_dropped_partition() -> None:
    texts = ["a " * 20, "b " * 20, "c " * 20]
    chunks = _make_chunks(texts)
    scores = [1.0, 0.9, 0.8]
    opt = TokenBudgetOptimizer(budget=30, size_unit="chars")
    result = opt.select(chunks, scores=scores)
    assert len(result.selected) + len(result.dropped) == len(chunks)


def test_scores_length_mismatch_raises() -> None:
    chunks = _make_chunks(["hello world"])
    opt = TokenBudgetOptimizer(budget=100)
    with pytest.raises(ValueError):
        opt.select(chunks, scores=[1.0, 2.0])


def test_invalid_budget_raises() -> None:
    with pytest.raises(ValueError):
        TokenBudgetOptimizer(budget=0)
    with pytest.raises(ValueError):
        TokenBudgetOptimizer(budget=-1)


def test_invalid_strategy_raises() -> None:
    with pytest.raises(ValueError):
        TokenBudgetOptimizer(budget=100, strategy="invalid")


def test_deduplication_removes_near_duplicates() -> None:
    text = "the quick brown fox " * 10
    chunks = _make_chunks([text, text + " extra", "completely different content"])
    scores = [1.0, 0.9, 0.5]
    opt = TokenBudgetOptimizer(
        budget=500,
        deduplicate_overlap=True,
        overlap_threshold=0.8,
        size_unit="chars",
    )
    result = opt.select(chunks, scores=scores)
    assert len(result.selected) <= 2


def test_no_scores_selects_in_order() -> None:
    texts = ["a " * 10 for _ in range(5)]
    chunks = _make_chunks(texts)
    opt = TokenBudgetOptimizer(budget=30, size_unit="chars")
    result = opt.select(chunks)
    assert result.total_tokens <= 30


def test_greedy_vs_dp_both_within_budget() -> None:
    texts = [f"word{i} " * 8 for i in range(20)]
    chunks = _make_chunks(texts)
    scores = [float(i % 5) for i in range(20)]
    for strategy in ("greedy", "dp"):
        opt = TokenBudgetOptimizer(budget=80, strategy=strategy, size_unit="chars")
        result = opt.select(chunks, scores=scores)
        assert result.total_tokens <= 80
        assert result.strategy == strategy

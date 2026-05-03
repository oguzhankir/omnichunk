from __future__ import annotations

import pytest

from omnichunk.budget import BudgetResult, TokenBudgetOptimizer
from omnichunk.budget import optimizer as optimizer_mod
from omnichunk.dedup import dedup_chunks
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


def _make_chunk(
    text: str,
    *,
    byte_start: int,
    index: int,
    total: int,
    token_count: int | None = None,
    nws_count: int | None = None,
    char_count: int | None = None,
    filepath: str = "f.py",
) -> Chunk:
    end = byte_start + len(text.encode("utf-8"))
    tc = len(text.split()) if token_count is None else token_count
    nc = sum(1 for c in text if not c.isspace()) if nws_count is None else nws_count
    cc = len(text) if char_count is None else char_count
    return Chunk(
        text=text,
        contextualized_text=text,
        byte_range=ByteRange(byte_start, end),
        line_range=LineRange(index, index),
        index=index,
        total_chunks=total,
        context=ChunkContext(filepath=filepath, language="python"),
        token_count=tc,
        char_count=cc,
        nws_count=nc,
    )


def _score_sum_by_index(selected: list[Chunk], scores: list[float]) -> float:
    """Sum scores for ``selected`` using each chunk's ``index`` into ``scores``."""
    return sum(scores[c.index] for c in selected)


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


def test_empty_chunk_list_returns_empty_budget_result() -> None:
    opt = TokenBudgetOptimizer(budget=50, strategy="dp")
    result = opt.select([])
    assert result == BudgetResult(
        selected=[],
        total_tokens=0,
        dropped=[],
        budget=50,
        strategy="dp",
    )


def test_single_chunk_exceeds_budget_selects_none() -> None:
    chunks = [_make_chunk("x" * 100, byte_start=0, index=0, total=1, char_count=100)]
    opt = TokenBudgetOptimizer(budget=10, size_unit="chars")
    result = opt.select(chunks, scores=[1.0])
    assert result.selected == []
    assert result.total_tokens == 0
    assert result.dropped == chunks


def test_all_chunks_fit_in_budget() -> None:
    texts = ["aa", "bbb", "c"]
    chunks = _make_chunks(texts)
    scores = [0.1, 0.2, 0.3]
    opt = TokenBudgetOptimizer(budget=100, strategy="dp", size_unit="chars")
    result = opt.select(chunks, scores=scores)
    assert len(result.selected) == 3
    assert result.dropped == []
    assert result.total_tokens == sum(c.char_count for c in chunks)


def test_chunk_size_exactly_equals_budget_fits_one() -> None:
    chunks = [
        _make_chunk("aaaa", byte_start=0, index=0, total=2, char_count=4),
        _make_chunk("bbbb", byte_start=10, index=1, total=2, char_count=4),
    ]
    scores = [1.0, 2.0]
    opt = TokenBudgetOptimizer(budget=4, strategy="dp", size_unit="chars")
    result = opt.select(chunks, scores=scores)
    assert result.total_tokens == 4
    assert len(result.selected) == 1
    assert result.selected[0].index == 1
    assert result.dropped[0].index == 0


def test_dedup_chunks_then_optimizer_preserves_source_order() -> None:
    a = _make_chunk("dup body", byte_start=0, index=0, total=4)
    b = _make_chunk("dup body", byte_start=20, index=1, total=4)
    c = _make_chunk("unique tail", byte_start=40, index=2, total=4)
    d = _make_chunk("other", byte_start=60, index=3, total=4)
    originals = [a, b, c, d]
    scores_full = [1.0, 0.9, 2.0, 0.5]
    unique, _dup_map = dedup_chunks(originals, method="exact")
    assert [c.index for c in unique] == [0, 2, 3]
    scores_unique = [scores_full[i] for i in (0, 2, 3)]
    opt = TokenBudgetOptimizer(budget=50, strategy="greedy", size_unit="chars")
    result = opt.select(unique, scores=scores_unique)
    assert [c.index for c in result.selected] == [0, 2, 3]


def test_dp_total_score_same_or_better_than_greedy() -> None:
    texts = ["aaa", "bbb", "ccccc"]
    chunks = _make_chunks(texts)
    scores = [3.0, 3.0, 5.0]
    budget = 6
    greedy_res = TokenBudgetOptimizer(
        budget=budget, strategy="greedy", size_unit="chars"
    ).select(chunks, scores=scores)
    dp_res = TokenBudgetOptimizer(budget=budget, strategy="dp", size_unit="chars").select(
        chunks, scores=scores
    )
    greedy_score = _score_sum_by_index(greedy_res.selected, scores)
    dp_score = _score_sum_by_index(dp_res.selected, scores)
    assert dp_score >= greedy_score
    assert greedy_score == 5.0
    assert dp_score == 6.0


def test_negative_or_zero_budget_raises_value_error() -> None:
    for bad in (0, -1, -100):
        with pytest.raises(ValueError, match="budget must be > 0"):
            TokenBudgetOptimizer(budget=bad)


def test_optimizer_deterministic_across_repeated_calls() -> None:
    chunks = _make_chunks(["alpha beta", "gamma", "delta epsilon"])
    scores = [2.0, 5.0, 1.0]
    opt = TokenBudgetOptimizer(budget=15, strategy="dp", size_unit="chars")
    first = opt.select(chunks, scores=scores)
    for _ in range(5):
        again = opt.select(chunks, scores=scores)
        assert again.selected == first.selected
        assert again.dropped == first.dropped
        assert again.total_tokens == first.total_tokens


def test_invalid_overlap_threshold_raises() -> None:
    with pytest.raises(ValueError, match="overlap_threshold"):
        TokenBudgetOptimizer(budget=10, overlap_threshold=0.0)
    with pytest.raises(ValueError, match="overlap_threshold"):
        TokenBudgetOptimizer(budget=10, overlap_threshold=1.5)


def test_preserve_order_false_skips_sort() -> None:
    low_first = _make_chunk("low", byte_start=0, index=0, total=2, char_count=3)
    high_second = _make_chunk("high", byte_start=100, index=1, total=2, char_count=3)
    chunks = [low_first, high_second]
    scores = [1.0, 10.0]
    opt = TokenBudgetOptimizer(
        budget=3, strategy="greedy", preserve_order=False, size_unit="chars"
    )
    result = opt.select(chunks, scores=scores)
    assert len(result.selected) == 1
    assert result.selected[0] is high_second


def test_size_unit_tokens_and_nws() -> None:
    t_chunk = _make_chunk("a b", byte_start=0, index=0, total=1, token_count=2, nws_count=2)
    opt_t = TokenBudgetOptimizer(budget=2, size_unit="tokens")
    assert opt_t.select([t_chunk], scores=[1.0]).total_tokens == 2
    nws_chunk = _make_chunk(" x ", byte_start=0, index=0, total=1, nws_count=1)
    opt_n = TokenBudgetOptimizer(budget=1, size_unit="nws")
    assert opt_n.select([nws_chunk], scores=[1.0]).total_tokens == 1


def test_dp_falls_back_to_greedy_when_state_space_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    greedy_calls: list[str] = []
    real_greedy = optimizer_mod._greedy_select

    def spy_greedy(
        c: list,
        s: list[float],
        b: int,
        su: str,
    ) -> list[int]:
        greedy_calls.append("greedy")
        return real_greedy(c, s, b, su)

    monkeypatch.setattr(optimizer_mod, "_greedy_select", spy_greedy)
    chunks = _make_chunks(["p", "q"])
    opt = TokenBudgetOptimizer(
        budget=25_000_001, strategy="dp", size_unit="chars"
    )
    opt.select(chunks, scores=[1.0, 2.0])
    assert greedy_calls == ["greedy"]


def test_jaccard_nws_empty_and_one_side_empty() -> None:
    assert optimizer_mod._jaccard_nws("", "") == 1.0
    assert optimizer_mod._jaccard_nws("", "a") == 0.0
    assert optimizer_mod._jaccard_nws("b", "") == 0.0


def test_deduplicate_keeps_higher_score_when_jaccard_high() -> None:
    body = "same tokens here"
    low = _make_chunk(body, byte_start=0, index=0, total=2, char_count=len(body))
    high = _make_chunk(body + " ", byte_start=50, index=1, total=2, char_count=len(body) + 1)
    opt = TokenBudgetOptimizer(
        budget=500,
        deduplicate_overlap=True,
        overlap_threshold=0.99,
        size_unit="chars",
    )
    result = opt.select([low, high], scores=[1.0, 5.0])
    assert len(result.selected) == 1
    assert result.selected[0] is high
    assert result.dropped == [low]

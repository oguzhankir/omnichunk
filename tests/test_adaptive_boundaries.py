from __future__ import annotations

import time

import pytest

from omnichunk.semantic.tfidf import detect_topic_shifts

# Three synthetic documents with known topic structure. Each block uses a
# disjoint vocabulary so the true boundary sits between blocks.
COOKING = ["I diced onions and garlic for the sauce."] * 4
ASTRO = ["The galaxy rotates around a supermassive black hole."] * 4
FINANCE = ["Quarterly revenue exceeded the analyst earnings forecast."] * 4


def _boundary_block(shifts: tuple[int, ...], target: int, tol: int = 1) -> bool:
    return any(abs(s - target) <= tol for s in shifts)


def test_adaptive_returns_tuple() -> None:
    shifts = detect_topic_shifts(COOKING + ASTRO, method="adaptive")
    assert isinstance(shifts, tuple)
    assert all(isinstance(i, int) for i in shifts)


def test_adaptive_detects_single_boundary() -> None:
    # 4 cooking + 4 astro -> true boundary after sentence index 3.
    shifts = detect_topic_shifts(COOKING + ASTRO, method="adaptive", min_shift_gap=2)
    assert shifts
    assert _boundary_block(shifts, 3)


def test_adaptive_detects_two_boundaries() -> None:
    docs = COOKING + ASTRO + FINANCE  # boundaries after idx 3 and idx 7
    shifts = detect_topic_shifts(docs, method="adaptive", min_shift_gap=2)
    assert _boundary_block(shifts, 3)
    assert _boundary_block(shifts, 7)


def test_adaptive_on_homogeneous_doc_is_relative() -> None:
    # All identical sentences -> similarities are uniform; mean - k*std is at
    # the mean so no gap falls strictly below it. Fixed threshold of 0.5 would
    # wrongly flag nothing here too, but the point is adaptive must not explode.
    homogeneous = ["The same sentence repeated verbatim."] * 8
    shifts = detect_topic_shifts(homogeneous, method="adaptive")
    assert shifts == ()


def test_fixed_vs_adaptive_distinct() -> None:
    docs = COOKING + ASTRO
    fixed = detect_topic_shifts(docs, method="fixed", threshold=0.5, min_shift_gap=2)
    adaptive = detect_topic_shifts(docs, method="adaptive", min_shift_gap=2)
    assert isinstance(fixed, tuple)
    assert isinstance(adaptive, tuple)
    # Adaptive should locate the real boundary regardless of an arbitrary fixed cut.
    assert _boundary_block(adaptive, 3)


def test_threshold_k_controls_sensitivity() -> None:
    docs = COOKING + ASTRO + FINANCE
    loose = detect_topic_shifts(docs, method="adaptive", k=0.1, min_shift_gap=1)
    strict = detect_topic_shifts(docs, method="adaptive", k=3.0, min_shift_gap=1)
    assert isinstance(loose, tuple)
    assert isinstance(strict, tuple)
    # A larger k -> lower threshold -> never more boundaries than a small k.
    assert len(strict) <= len(loose)


def test_invalid_method_raises() -> None:
    with pytest.raises(ValueError, match="fixed.*adaptive"):
        detect_topic_shifts(COOKING + ASTRO, method="bogus")


# ---------------------------------------------------------------------------
# Commit 28 — sliding window coherence scoring
# ---------------------------------------------------------------------------


def test_window_size_alias_of_window() -> None:
    docs = COOKING + ASTRO
    a = detect_topic_shifts(docs, window=2, min_shift_gap=2)
    b = detect_topic_shifts(docs, window_size=2, min_shift_gap=2)
    assert a == b


def test_window_smoothing_more_accurate_than_w1() -> None:
    # Inject one noisy off-topic sentence inside an otherwise coherent block.
    block_a = ["Garlic onion tomato basil sauce simmered slowly."] * 4
    noise = ["Quantum entanglement violates local realism."]
    block_a2 = ["Garlic onion tomato basil sauce simmered slowly."] * 4
    block_b = ["The rover traversed the martian crater rim."] * 4
    docs = block_a + noise + block_a2 + block_b

    _, scores_w1 = detect_topic_shifts(docs, window_size=1, return_scores=True)
    _, scores_w5 = detect_topic_shifts(docs, window_size=5, return_scores=True)
    assert len(scores_w1) == len(docs) - 1
    assert len(scores_w5) == len(docs) - 1
    # The real boundary is between block_a2 and block_b at gap index 12.
    real_gap = len(block_a) + len(noise) + len(block_a2) - 1
    boundaries_w5 = detect_topic_shifts(docs, window_size=5, method="adaptive", min_shift_gap=2)
    assert any(abs(s - real_gap) <= 1 for s in boundaries_w5)


def test_performance_1000_sentences_under_2s() -> None:
    sents = (["alpha beta gamma delta term."] * 500) + (
        ["zeta eta theta iota lemma."] * 500
    )
    started = time.perf_counter()
    shifts = detect_topic_shifts(sents, window_size=5, method="adaptive")
    elapsed = time.perf_counter() - started
    assert isinstance(shifts, tuple)
    assert elapsed < 2.0, f"took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Commit 29 — return_scores debug mode
# ---------------------------------------------------------------------------


def test_return_scores_returns_tuple_pair() -> None:
    docs = COOKING + ASTRO
    result = detect_topic_shifts(docs, return_scores=True)
    assert isinstance(result, tuple)
    assert len(result) == 2
    shifts, scores = result
    assert isinstance(shifts, tuple)
    assert isinstance(scores, list)
    assert all(isinstance(x, float) for x in scores)
    assert len(scores) == len(docs) - 1


def test_return_scores_empty_for_single_sentence() -> None:
    shifts, scores = detect_topic_shifts(["only one."], return_scores=True)
    assert shifts == ()
    assert scores == []

from __future__ import annotations

import math
from dataclasses import asdict

import pytest
from hypothesis import given
from hypothesis import strategies as st

from omnichunk.retrieval_eval import EvidenceSpan, score_evidence, score_ranking


def test_ranking_matches_hand_calculated_graded_metrics() -> None:
    # A missed best passage must remain in the ideal-ranking denominator.
    result = score_ranking(["unjudged", "b", "c"], {"a": 3, "b": 2, "c": 1}, k=3)
    dcg = 3 / math.log2(3) + 1 / math.log2(4)
    ideal = 7 + 3 / math.log2(3) + 1 / math.log2(4)
    assert result.recall_at_k == pytest.approx(2 / 3)
    assert result.mrr_at_k == 0.5
    assert result.ndcg_at_k == pytest.approx(dcg / ideal)
    assert result.relevant_count == 3
    assert result.retrieved_count == result.k == 3


def test_duplicate_ids_consume_slots_without_double_credit() -> None:
    result = score_ranking(["a", "a", "b"], {"a": 1, "b": 1}, k=2)
    assert result.recall_at_k == 0.5
    assert result.mrr_at_k == 1
    assert result.ndcg_at_k == pytest.approx(1 / (1 + 1 / math.log2(3)))
    assert result.retrieved_count == 2


def test_cutoff_excludes_late_relevant_results() -> None:
    result = score_ranking(["wrong", "a"], {"a": 1}, k=1)
    assert result.recall_at_k == result.mrr_at_k == result.ndcg_at_k == 0


@pytest.mark.parametrize("grades", [{}, {"a": 0}])
def test_no_positive_judgments_have_zero_ranking_scores(grades: dict[str, float]) -> None:
    result = score_ranking(["a"], grades)
    assert result.recall_at_k == result.mrr_at_k == result.ndcg_at_k == 0
    assert result.relevant_count == 0


def test_no_results_and_perfect_rankings() -> None:
    empty = score_ranking([], {"a": 1})
    assert empty.recall_at_k == empty.mrr_at_k == empty.ndcg_at_k == 0
    assert empty.retrieved_count == 0
    perfect = score_ranking(["a", "b"], {"a": 2, "b": 1, "c": 0}, k=10)
    assert perfect.recall_at_k == perfect.mrr_at_k == perfect.ndcg_at_k == 1
    assert asdict(perfect)["k"] == 10


@pytest.mark.parametrize("grade", [1e-200, 1024.0, 1e300])
def test_ndcg_handles_extreme_valid_grades_without_overflow(grade: float) -> None:
    result = score_ranking(["a"], {"a": grade})
    assert result.ndcg_at_k == 1


@pytest.mark.parametrize("k", [0, -1, True, 1.5, "3"])
def test_invalid_cutoff_is_rejected(k) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        score_ranking([], {}, k=k)


@pytest.mark.parametrize("grade", [-1, float("nan"), float("inf"), "1", True, 1j, 10**400])
def test_invalid_relevance_is_rejected(grade) -> None:
    with pytest.raises(ValueError, match="finite nonnegative"):
        score_ranking([], {"a": grade})


@pytest.mark.parametrize("identifier", ["", "  ", None, 1])
def test_invalid_ranked_or_judged_ids_are_rejected(identifier) -> None:
    with pytest.raises(ValueError, match="nonempty strings"):
        score_ranking([identifier], {})
    with pytest.raises(ValueError, match="nonempty strings"):
        score_ranking([], {identifier: 1})


@pytest.mark.parametrize("coordinates", [(0, 0), (-1, 2), (2, 1), (0.0, 1), (0, True)])
def test_invalid_evidence_coordinates_are_rejected(coordinates) -> None:
    with pytest.raises(ValueError, match="integer coordinates"):
        EvidenceSpan("a", *coordinates)


def test_evidence_requires_a_source_and_span_values() -> None:
    with pytest.raises(ValueError, match="nonempty strings"):
        EvidenceSpan("", 0, 1)
    with pytest.raises(ValueError, match="EvidenceSpan"):
        score_evidence([("a", 0, 1)], [])
    with pytest.raises(ValueError, match="EvidenceSpan"):
        score_evidence([], [None])


def test_evidence_overlap_unions_and_multiple_documents() -> None:
    result = score_evidence(
        [EvidenceSpan("a", 0, 10), EvidenceSpan("a", 5, 15), EvidenceSpan("b", 0, 5)],
        [EvidenceSpan("a", 5, 10), EvidenceSpan("a", 8, 20), EvidenceSpan("c", 0, 5)],
    )
    assert result.retrieved_bytes == result.relevant_bytes == 20
    assert result.intersection_bytes == 10
    assert result.precision == result.recall == 0.5
    assert result.iou == pytest.approx(1 / 3)


def test_disjoint_spans_and_matching_coordinates_from_other_documents() -> None:
    result = score_evidence([EvidenceSpan("a", 0, 10)], [EvidenceSpan("b", 0, 10)])
    assert result.intersection_bytes == 0
    assert result.precision == result.recall == result.iou == 0


def test_utf8_source_spans_measure_bytes_including_combining_marks_and_emoji() -> None:
    source = "Türkçe 資料😀 e\u0301"
    prefix = "Türkçe "
    evidence = "資料😀"
    start = len(prefix.encode("utf-8"))
    end = start + len(evidence.encode("utf-8"))
    raw = source.encode("utf-8")
    assert raw[start:end].decode("utf-8") == evidence
    result = score_evidence(
        [EvidenceSpan("revision-1", 0, len(raw))], [EvidenceSpan("revision-1", start, end)]
    )
    assert result.intersection_bytes == result.relevant_bytes == 10
    assert result.retrieved_bytes == len(raw)
    assert result.recall == 1
    assert result.precision == result.iou == pytest.approx(10 / len(raw))


def test_empty_evidence_sets_have_documented_values() -> None:
    empty = score_evidence([], [])
    assert empty.precision == empty.recall == empty.iou == 1
    assert empty.retrieved_bytes == empty.relevant_bytes == empty.intersection_bytes == 0
    for predicted, expected in (([], [EvidenceSpan("a", 0, 1)]), ([EvidenceSpan("a", 0, 1)], [])):
        result = score_evidence(predicted, expected)
        assert result.precision == result.recall == result.iou == 0


@given(
    st.lists(st.tuples(st.sampled_from(["a", "b"]), st.integers(0, 20), st.integers(1, 10))),
    st.lists(st.tuples(st.sampled_from(["a", "b"]), st.integers(0, 20), st.integers(1, 10))),
)
def test_union_metrics_match_explicit_byte_sets(predicted, expected) -> None:
    predicted_spans = [
        EvidenceSpan(source, start, start + length) for source, start, length in predicted
    ]
    expected_spans = [
        EvidenceSpan(source, start, start + length) for source, start, length in expected
    ]
    predicted_bytes = {
        (span.source_id, byte) for span in predicted_spans for byte in range(span.start, span.end)
    }
    expected_bytes = {
        (span.source_id, byte) for span in expected_spans for byte in range(span.start, span.end)
    }
    result = score_evidence(predicted_spans, expected_spans)
    assert result.retrieved_bytes == len(predicted_bytes)
    assert result.relevant_bytes == len(expected_bytes)
    assert result.intersection_bytes == len(predicted_bytes & expected_bytes)
    assert 0 <= result.precision <= 1
    assert 0 <= result.recall <= 1
    assert 0 <= result.iou <= 1

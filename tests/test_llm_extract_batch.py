from __future__ import annotations

import json
import time

from omnichunk.propositions.llm_extract import (
    extract_propositions_llm_batch,
    extract_propositions_stream,
)


def _make_batch_llm(counter: dict[str, int]):
    """Mock batched LLM: echoes each chunk's text as a single verbatim claim."""

    def llm(_filepath: str, payload: str) -> str:
        counter["calls"] += 1
        data = json.loads(payload)
        results = []
        for ch in data["chunks"]:
            results.append({"claims": [{"text": ch["text"].strip(), "confidence": 0.8}]})
        return json.dumps({"results": results})

    return llm


def test_batch_reduces_call_count_proportionally() -> None:
    chunks = ["Alpha is one.", "Beta is two.", "Gamma is three.", "Delta is four."]

    c1: dict[str, int] = {"calls": 0}
    extract_propositions_llm_batch(chunks, llm_fn=_make_batch_llm(c1), batch_size=1)
    assert c1["calls"] == 4

    c2: dict[str, int] = {"calls": 0}
    extract_propositions_llm_batch(chunks, llm_fn=_make_batch_llm(c2), batch_size=2)
    assert c2["calls"] == 2

    c4: dict[str, int] = {"calls": 0}
    extract_propositions_llm_batch(chunks, llm_fn=_make_batch_llm(c4), batch_size=4)
    assert c4["calls"] == 1


def test_batch_preserves_chunk_order() -> None:
    chunks = ["First claim here.", "Second claim here.", "Third claim here."]
    props, warns = extract_propositions_llm_batch(
        chunks, llm_fn=_make_batch_llm({"calls": 0}), batch_size=3
    )
    assert not warns
    assert [p.text for p in props] == [
        "First claim here.",
        "Second claim here.",
        "Third claim here.",
    ]
    assert [p.metadata["chunk_index"] for p in props] == [0, 1, 2]


def test_batch_byte_ranges_relative_to_each_chunk() -> None:
    chunks = ["The cat sat.", "The dog ran."]
    props, _ = extract_propositions_llm_batch(
        chunks, llm_fn=_make_batch_llm({"calls": 0}), batch_size=2
    )
    for p in props:
        idx = p.metadata["chunk_index"]
        raw = chunks[idx].encode("utf-8")
        assert raw[p.byte_range.start : p.byte_range.end].decode("utf-8") == p.text


def test_stream_yields_in_order() -> None:
    chunks = ["One fact here.", "Two fact here.", "Three fact here."]
    streamed = list(
        extract_propositions_stream(
            chunks, llm_fn=_make_batch_llm({"calls": 0}), batch_size=1
        )
    )
    assert [p.text for p in streamed] == [
        "One fact here.",
        "Two fact here.",
        "Three fact here.",
    ]


def test_retry_with_exponential_backoff() -> None:
    state = {"calls": 0}
    delays: list[float] = []

    def flaky_llm(_fp: str, payload: str) -> str:
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("transient API error")
        data = json.loads(payload)
        results = [{"claims": [{"text": c["text"].strip()}]} for c in data["chunks"]]
        return json.dumps({"results": results})

    props, warns = extract_propositions_llm_batch(
        ["Recoverable claim here."],
        llm_fn=flaky_llm,
        batch_size=1,
        max_retries=3,
        retry_delays=(1.0, 2.0, 4.0),
        sleep_fn=delays.append,
    )
    # Two failures -> two backoff sleeps using the first two delays, then success.
    assert delays == [1.0, 2.0]
    assert len(props) == 1
    assert any("failed" in w for w in warns)


def test_retry_exhausted_returns_empty_with_warnings() -> None:
    def always_fails(_fp: str, _payload: str) -> str:
        raise RuntimeError("permanent failure")

    props, warns = extract_propositions_llm_batch(
        ["Some claim."],
        llm_fn=always_fails,
        batch_size=1,
        max_retries=3,
        retry_delays=(0.0, 0.0, 0.0),
        sleep_fn=lambda _d: None,
    )
    assert props == []
    assert any("no result after retries" in w for w in warns)


def test_timeout_cancels_slow_call() -> None:
    def slow_llm(_fp: str, _payload: str) -> str:
        time.sleep(0.3)
        return json.dumps({"results": []})

    props, warns = extract_propositions_llm_batch(
        ["A claim that never returns in time."],
        llm_fn=slow_llm,
        batch_size=1,
        timeout=0.05,
        max_retries=2,
        retry_delays=(0.0, 0.0),
        sleep_fn=lambda _d: None,
    )
    assert props == []
    assert any("timed out" in w for w in warns)

"""Markdown paragraph identity and owning-heading regressions."""

from __future__ import annotations

import pytest

from omnichunk import Chunker


@pytest.mark.parametrize("minimum", [0, 80])
def test_markdown_keeps_distinct_fitting_paragraphs_with_spare_capacity(minimum: int) -> None:
    paragraphs = [
        "The gardener waters newly planted trees.",
        "An auditor signs the quarterly accounts.",
        "A mechanic checks the brake fluid level.",
    ]
    source = "# Handbook\n\n" + "\n\n".join(paragraphs) + "\n"
    chunks = Chunker(
        max_chunk_size=256,
        min_chunk_size=minimum,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("handbook.md", source)

    assert len(chunks) == 3
    assert "".join(chunk.text for chunk in chunks) == source
    assert chunks[0].text.startswith("# Handbook\n\n" + paragraphs[0])
    assert all(sum(paragraph in chunk.text for paragraph in paragraphs) == 1 for chunk in chunks)
    assert all(chunk.context.heading_hierarchy == ["Handbook"] for chunk in chunks)


def test_nested_headings_keep_the_context_of_their_following_paragraph() -> None:
    source = (
        "# Manual\n\nRead the introduction.\n\n"
        "## Billing\n\nInvoices require approval.\n\n"
        "## Logs\n\nEvents retain the source reference.\n"
    )
    chunks = Chunker(
        max_chunk_size=256,
        min_chunk_size=100,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("manual.md", source)

    assert "".join(chunk.text for chunk in chunks) == source
    assert [chunk.context.heading_hierarchy for chunk in chunks] == [
        ["Manual"],
        ["Manual", "Billing"],
        ["Manual", "Logs"],
    ]
    assert all("## Billing" not in chunk.text for chunk in chunks if "introduction" in chunk.text)


def test_parent_and_child_heading_prefix_uses_the_body_owning_path() -> None:
    source = "# Manual\n\n## Billing\n\nInvoices require approval.\n"
    chunks = Chunker(
        max_chunk_size=256,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("manual.md", source)

    assert [chunk.text for chunk in chunks] == [source]
    assert chunks[0].context.heading_hierarchy == ["Manual", "Billing"]


def test_paragraph_identity_preserves_native_style_token_budgets_and_utf8_ranges() -> None:
    paragraphs = [
        "Yazar değişikliği kaydeder. 😀",
        "資料を確認してから承認する。",
        "Keep references intact.",
    ]
    source = "# Review\r\n\r\n" + "\r\n\r\n".join(paragraphs) + "\r\n"

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2 + (12 if "# Review" in text and "Yazar" in text else 0)

    chunker = Chunker(
        max_chunk_size=96,
        min_chunk_size=80,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk("review.md", source)

    assert len(chunks) == 3
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    cursor = 0
    for chunk in chunks:
        assert chunk.byte_range.start == cursor
        cursor = chunk.byte_range.end
        assert raw[chunk.byte_range.start : cursor].decode("utf-8") == chunk.text
        assert count(chunk.contextualized_text) <= 96
    assert cursor == len(raw)
    assert [chunk.text for chunk in chunker.stream("review.md", source)] == [
        chunk.text for chunk in chunks
    ]


def test_plaintext_retains_its_existing_fitting_paragraph_packing() -> None:
    source = "Read the introduction.\n\nInvoices require approval.\n\nKeep references intact."
    chunks = Chunker(
        max_chunk_size=256,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("manual.txt", source)

    assert [chunk.text for chunk in chunks] == [source]

"""Public regressions for structural prose boundaries and measured payloads."""

from __future__ import annotations

import tracemalloc
from collections.abc import Callable
from dataclasses import replace

import pytest

from omnichunk import Chunker
from omnichunk.types import Chunk, ChunkingError


def test_token_grouping_does_not_retain_growing_source_prefixes() -> None:
    source = ("word " * 20 + "\n\n") * 1000
    chunker = Chunker(
        max_chunk_size=128_000,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=lambda text: len(text) // 4,
        context_mode="none",
        coverage_policy="lossless",
    )

    tracemalloc.start()
    try:
        chunks = chunker.chunk("notes.txt", source)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert [chunk.text for chunk in chunks] == [source]
    # The old grouping probes cached ~49 MiB of progressively larger prefixes
    # for this 100 KiB input. Allow generous space for source indexes and chunks
    # without accepting retention of the transient prefix series.
    assert peak < 24 * 1024 * 1024


def assert_source_and_budget(
    chunks: list[Chunk], source: str, limit: int, count: Callable[[str], int] = len
) -> None:
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    cursor = 0
    for chunk in chunks:
        assert chunk.byte_range.start == cursor
        cursor = chunk.byte_range.end
        assert raw[chunk.byte_range.start : cursor].decode("utf-8") == chunk.text
        assert count(chunk.contextualized_text) <= limit
    assert cursor == len(raw)


@pytest.mark.parametrize("minimum", [0, 40, 80])
def test_fitting_markdown_paragraphs_survive_short_heading_and_minimum(minimum: int) -> None:
    paragraphs = [
        "A replacement key is activated only after every worker confirms receipt.",
        "The previous key stays available until all pending requests have finished.",
        "An operator records the reason before removing the retired key from storage.",
    ]
    source = "# Key rotation\n\n" + "\n\n".join(paragraphs) + "\n"
    chunks = Chunker(
        max_chunk_size=100,
        min_chunk_size=minimum,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("rotation.md", source)

    assert_source_and_budget(chunks, source, 100)
    for paragraph in paragraphs:
        assert any(paragraph in chunk.text for chunk in chunks)


def test_fitting_markdown_table_rows_remain_whole() -> None:
    rows = [
        "| Editor | May propose changes | Cannot approve their own proposal. |",
        "| Reviewer | May approve changes | Must record the approval reason. |",
        "| Owner | May revoke access | Must notify the document maintainer. |",
    ]
    source = "# Access\n\n| Role | Action | Restriction |\n| --- | --- | --- |\n"
    source += "\n".join(rows) + "\n"
    chunks = Chunker(
        max_chunk_size=100,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("access.md", source)

    assert_source_and_budget(chunks, source, 100)
    for row in rows:
        assert any(row in chunk.text for chunk in chunks)


def test_oversized_table_row_does_not_fragment_following_fitting_row() -> None:
    long_row = "| Exception | " + "A reviewer supplies supporting evidence. " * 8 + "|\n"
    following_row = "| Standard | The owner records the approval and closes the request. |"
    source = "| Type | Procedure |\n| --- | --- |\n" + long_row + following_row + "\n"
    chunks = Chunker(
        max_chunk_size=90,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("procedures.md", source)

    assert_source_and_budget(chunks, source, 90)
    assert any(following_row in chunk.text for chunk in chunks)
    assert len(chunks) > 3


@pytest.mark.parametrize("source", ["alpha\n\nbravo\n\n", "  alpha\n\nbravo  \n\n\n\n"])
def test_prose_grouping_counts_gaps_and_trailing_whitespace(source: str) -> None:
    chunks = Chunker(
        max_chunk_size=10,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    assert_source_and_budget(chunks, source, 10)
    assert any("alpha" in chunk.text for chunk in chunks)
    assert any("bravo" in chunk.text for chunk in chunks)


def test_prose_grouping_measures_nonadditive_token_cost_of_joined_nodes() -> None:
    def count(text: str) -> int:
        # A tokenizer can assign a different cost across a concatenation boundary.
        return len(text) + (20 if "alpha" in text and "bravo" in text else 0)

    source = "alpha\n\nbravo"
    chunks = Chunker(
        max_chunk_size=20,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
        overflow_policy="error",
    ).chunk("notes.txt", source)

    assert_source_and_budget(chunks, source, 20, count)
    assert any("alpha" in chunk.text for chunk in chunks)
    assert any("bravo" in chunk.text for chunk in chunks)


def test_prose_grouping_can_join_nodes_when_token_cost_decreases() -> None:
    def count(text: str) -> int:
        return len(text.replace("left\n\nright", "X"))

    source = "left\n\nright"
    chunks = Chunker(
        max_chunk_size=5,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    assert_source_and_budget(chunks, source, 5, count)
    assert [chunk.text for chunk in chunks] == [source]


@pytest.mark.parametrize("filepath", ["notes.txt", "notes.md"])
def test_oversized_prose_respects_explicit_error_and_preserve_policies(filepath: str) -> None:
    source = "unbroken" * 12
    chunker = Chunker(
        max_chunk_size=16,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )

    with pytest.raises(ChunkingError, match="exceeds"):
        chunker.chunk(filepath, source, overflow_policy="error")

    preserved = chunker.chunk(filepath, source, overflow_policy="preserve")
    assert [chunk.text for chunk in preserved] == [source]
    assert preserved[0].byte_range.start == 0
    assert preserved[0].byte_range.end == len(source.encode("utf-8"))
    assert preserved[0].metadata["budget"]["overflow"] == len(source) - 16


@pytest.mark.parametrize(
    ("sentences", "separator", "limit"),
    [
        (
            [
                "İlk kayıt denetim günlüğüne güvenle yazılır.",
                "Şüpheli kayıtlar ayrı bir incelemeye gönderilir.",
                "Üçüncü deneme yetkili onayıyla başlatılır.",
            ],
            " ",
            60,
        ),
        (
            [
                "最初の記録は監査ログに保存する。",
                "担当者は不審な記録を確認してから承認する。",
                "再試行する場合は承認者とその理由を記録する。",
            ],
            "",
            30,
        ),
    ],
)
def test_fitting_unicode_sentences_stay_whole_in_oversized_paragraph(
    sentences: list[str], separator: str, limit: int
) -> None:
    source = separator.join(sentences)
    chunks = Chunker(
        max_chunk_size=limit,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("instructions.txt", source)

    assert_source_and_budget(chunks, source, limit)
    for sentence in sentences:
        assert any(sentence in chunk.text for chunk in chunks)


def test_word_fallback_packs_many_short_words_without_fragmentation() -> None:
    source = "red blue green " * 20
    chunks = Chunker(
        max_chunk_size=60,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("labels.txt", source)

    assert_source_and_budget(chunks, source, 60)
    assert len(chunks) <= 6
    assert all(len(chunk.text) >= 50 for chunk in chunks[:-1])


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_unicode_paragraph_boundaries_preserve_bytes_and_stream_parity(newline: str) -> None:
    paragraphs = [
        "İnceleyici, değişikliği onaylamadan önce kaynak belgeyi doğrular. 😀",
        "資料の変更は確認を受けてから公開する。担当者は変更理由と元の参照を残す。",
        "A cafe\u0301 owner keeps the original spelling when publishing a correction.",
    ]
    source = "# Review" + newline * 2 + (newline * 2).join(paragraphs) + newline
    chunker = Chunker(
        max_chunk_size=90,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk("review.md", source)
    streamed = list(chunker.stream("review.md", source))

    assert_source_and_budget(chunks, source, 90)
    for paragraph in paragraphs:
        assert any(paragraph in chunk.text for chunk in chunks)
    assert all(chunk.total_chunks == -1 for chunk in streamed)
    assert [replace(chunk, total_chunks=len(streamed)) for chunk in streamed] == chunks

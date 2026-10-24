from __future__ import annotations

from pathlib import Path

import pytest

from omnichunk import Chunker
from omnichunk.engine.prose_engine import _windows_to_contiguous_ranges
from omnichunk.types import ContentType


def test_markdown_chunking_with_heading_context(fixtures_dir: Path) -> None:
    md = (fixtures_dir / "markdown_doc.md").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=280, min_chunk_size=60, size_unit="chars", overlap_lines=1)

    chunks = chunker.chunk("docs/guide.md", md)

    assert len(chunks) > 1
    assert "".join(c.text for c in chunks) == md
    assert any(c.context.heading_hierarchy for c in chunks)
    assert all(
        c.context.content_type in {ContentType.PROSE, ContentType.CODE, ContentType.MARKUP}
        for c in chunks
    )
    assert any(c.context.content_type == ContentType.PROSE for c in chunks)


def test_markdown_detects_code_block_sections(fixtures_dir: Path) -> None:
    md = (fixtures_dir / "markdown_doc.md").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=180, min_chunk_size=50, size_unit="chars")

    chunks = chunker.chunk("README.md", md)
    section_types = {c.context.section_type for c in chunks}

    assert "code_block" in section_types or any("```" in c.text for c in chunks)


def test_markdown_fenced_code_routes_to_code_engine(fixtures_dir: Path) -> None:
    md = (fixtures_dir / "markdown_doc.md").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=120, min_chunk_size=30, size_unit="chars")

    chunks = chunker.chunk("docs/guide.md", md)
    code_chunks = [c for c in chunks if c.context.content_type == ContentType.CODE]

    assert code_chunks
    assert any("def get_token" in c.text for c in code_chunks)
    assert any(any(e.name == "get_token" for e in c.context.entities) for c in code_chunks)


def test_markdown_fenced_markup_routes_to_markup_engine(fixtures_dir: Path) -> None:
    md = (fixtures_dir / "markdown_doc.md").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=120, min_chunk_size=30, size_unit="chars")

    chunks = chunker.chunk("docs/guide.md", md)
    markup_chunks = [c for c in chunks if c.context.content_type == ContentType.MARKUP]

    assert markup_chunks
    assert any('"name": "Jane Doe"' in c.text for c in markup_chunks)
    assert all(c.context.section_type == "code_block" for c in markup_chunks)


def test_plaintext_semantic_split() -> None:
    text = (
        "Intro paragraph with context.\n\n"
        "Second paragraph has more sentences. It should split cleanly, not mid-word.\n\n"
        "Third paragraph is here for extra length."
    )
    chunker = Chunker(
        max_chunk_size=70, min_chunk_size=15, size_unit="chars", coverage_policy="lossless"
    )

    chunks = chunker.chunk("notes.txt", text)

    assert len(chunks) >= 2
    assert "".join(c.text for c in chunks) == text
    assert all(c.text for c in chunks)  # lossless mode may retain trivia-only spans


def test_windows_to_contiguous_ranges_preserves_contiguous_cursor_model() -> None:
    windows = [
        [(5, 12, [], "paragraph")],
        [(12, 20, [], "paragraph")],
    ]

    ranges = _windows_to_contiguous_ranges(windows, total_len=20)

    assert ranges
    assert ranges[0][0] == 0
    assert ranges[-1][1] == 20


@pytest.mark.parametrize("filepath", ["document.txt", "document.md"])
@pytest.mark.parametrize("unit", ["chars", "nws", "tokens"])
def test_unbroken_prose_uses_budget_without_single_character_fragmentation(filepath, unit):
    # CJK text, identifiers and encoded data often have no ASCII delimiters.
    text = "資料😀" * 333 + "末"
    chunker = Chunker(
        max_chunk_size=256,
        min_chunk_size=0,
        size_unit=unit,
        tokenizer=len if unit == "tokens" else None,
        context_mode="none",
        coverage_policy="lossless",
    )

    chunks = chunker.chunk(filepath, text)

    assert [len(c.text) for c in chunks] == [256, 256, 256, 232]
    assert "".join(c.text for c in chunks) == text
    raw = text.encode()
    assert all(raw[c.byte_range.start : c.byte_range.end].decode() == c.text for c in chunks)


def test_prose_hard_split_can_complete_a_multichar_token():
    def count(text):
        return 1 if text in {"ab", "cd", "ef"} else len(text) * 2

    chunks = Chunker(
        max_chunk_size=1,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("document.txt", "abcdef")

    assert [c.text for c in chunks] == ["ab", "cd", "ef"]
    assert all(c.metadata["budget"]["size"] <= 1 for c in chunks)

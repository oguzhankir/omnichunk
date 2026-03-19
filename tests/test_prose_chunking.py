from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
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
    chunker = Chunker(max_chunk_size=70, min_chunk_size=15, size_unit="chars")

    chunks = chunker.chunk("notes.txt", text)

    assert len(chunks) >= 2
    assert "".join(c.text for c in chunks) == text
    assert all(c.text.strip() for c in chunks)

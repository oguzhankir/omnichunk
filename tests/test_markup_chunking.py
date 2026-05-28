from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
from omnichunk.types import ContentType


def test_json_chunking_by_top_level_keys(fixtures_dir: Path) -> None:
    content = (fixtures_dir / "sample.json").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=120, min_chunk_size=20, size_unit="chars")

    chunks = chunker.chunk("config.json", content)

    assert chunks
    assert "".join(c.text for c in chunks) == content
    assert all(c.context.content_type == ContentType.MARKUP for c in chunks)
    assert any(c.context.breadcrumb for c in chunks)


def test_yaml_chunking(fixtures_dir: Path) -> None:
    content = (fixtures_dir / "sample.yaml").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=80, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("settings.yaml", content)

    assert chunks
    assert "".join(c.text for c in chunks) == content
    assert any(
        "app" in "/".join(c.context.breadcrumb) or "database" in "/".join(c.context.breadcrumb)
        for c in chunks
    )


def test_toml_chunking(fixtures_dir: Path) -> None:
    content = (fixtures_dir / "sample.toml").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=70, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("settings.toml", content)

    assert chunks
    assert "".join(c.text for c in chunks) == content


def test_html_chunking(fixtures_dir: Path) -> None:
    html = (fixtures_dir / "html_page.html").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=140, min_chunk_size=20, size_unit="chars")

    chunks = chunker.chunk("page.html", html)

    assert chunks
    assert "".join(c.text for c in chunks) == html
    assert any(c.context.section_type == "element" for c in chunks)


# ---------------------------------------------------------------------------
# Phase 2 — Markdown front matter + GFM/Obsidian callouts (Commit 21)
# ---------------------------------------------------------------------------


from omnichunk import Chunker as _Chunker


def test_markdown_frontmatter_parsed_into_metadata() -> None:
    src = "---\ntitle: My Doc\nauthor: Ada\ntags: rag, chunking\n---\n\n# Body\n\nText.\n"
    chunks = _Chunker(max_chunk_size=200, min_chunk_size=10, size_unit="chars").chunk(
        "doc.md", src
    )
    fm_chunk = next(c for c in chunks if c.context.section_type == "frontmatter")
    fm = fm_chunk.context.format_metadata.get("front_matter")
    assert isinstance(fm, dict)
    assert fm.get("title") == "My Doc"
    assert fm.get("author") == "Ada"
    assert fm.get("tags") == "rag, chunking"


def test_markdown_no_frontmatter_no_metadata_key() -> None:
    src = "# Heading\n\nNo frontmatter at all.\n"
    chunks = _Chunker(max_chunk_size=200, min_chunk_size=10, size_unit="chars").chunk(
        "doc.md", src
    )
    for ch in chunks:
        assert "front_matter" not in ch.context.format_metadata


def test_markdown_gfm_note_callout_detected() -> None:
    src = "# Title\n\n> [!NOTE]\n> Important info.\n\nRegular paragraph.\n"
    chunks = _Chunker(max_chunk_size=80, min_chunk_size=5, size_unit="chars").chunk(
        "doc.md", src
    )
    callout_chunks = [c for c in chunks if c.context.format_metadata.get("callout") == "note"]
    assert callout_chunks
    assert callout_chunks[0].context.section_type == "callout/note"


def test_markdown_gfm_warning_callout_detected() -> None:
    src = "# Title\n\n> [!WARNING]\n> Watch out.\n\nMore text.\n"
    chunks = _Chunker(max_chunk_size=80, min_chunk_size=5, size_unit="chars").chunk(
        "doc.md", src
    )
    callouts = {c.context.format_metadata.get("callout") for c in chunks}
    assert "warning" in callouts


def test_markdown_obsidian_lowercase_callout_detected() -> None:
    src = "> [!info]\n> Obsidian-style callout.\n\nBody.\n"
    chunks = _Chunker(max_chunk_size=80, min_chunk_size=5, size_unit="chars").chunk(
        "doc.md", src
    )
    info_callouts = [c for c in chunks if c.context.format_metadata.get("callout") == "info"]
    assert info_callouts


def test_markdown_frontmatter_reconstruction_intact() -> None:
    src = "---\nfoo: bar\n---\n\n# Heading\n\nBody.\n"
    chunks = _Chunker(max_chunk_size=200, min_chunk_size=10, size_unit="chars").chunk(
        "doc.md", src
    )
    assert "".join(c.text for c in chunks) == src


def test_markdown_callout_type_is_lowercased() -> None:
    """[!TIP] / [!Tip] / [!tip] all surface as 'tip'."""
    for marker in ("TIP", "Tip", "tip"):
        src = f"> [!{marker}]\n> Hello\n"
        chunks = _Chunker(max_chunk_size=80, min_chunk_size=5, size_unit="chars").chunk(
            "doc.md", src
        )
        assert any(c.context.format_metadata.get("callout") == "tip" for c in chunks)


def test_markdown_plain_blockquote_not_marked_callout() -> None:
    src = "> Just a regular quote without callout marker.\n"
    chunks = _Chunker(max_chunk_size=80, min_chunk_size=5, size_unit="chars").chunk(
        "doc.md", src
    )
    for ch in chunks:
        assert "callout" not in ch.context.format_metadata

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
    assert any("app" in "/".join(c.context.breadcrumb) or "database" in "/".join(c.context.breadcrumb) for c in chunks)


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

from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
from omnichunk.formats.rst import (
    _extract_section_headings,
    detect_rst_directives,
    load_rst,
)


def test_rst_loader_segments_code_block(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sample.rst").read_text(encoding="utf-8")
    doc = load_rst(code)
    assert doc.format_name == "rst"
    assert doc.text == code
    kinds = [s.kind for s in doc.segments]
    assert "code" in kinds and "prose" in kinds


def test_rst_chunk_reconstruction(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sample.rst").read_text(encoding="utf-8")
    chunks = Chunker(max_chunk_size=300, min_chunk_size=20, size_unit="chars").chunk(
        "doc.rst", code
    )
    assert chunks
    assert "".join(c.text for c in chunks) == code


def test_rst_chunk_byte_ranges_contiguous(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sample.rst").read_text(encoding="utf-8")
    chunks = Chunker(max_chunk_size=300, min_chunk_size=20, size_unit="chars").chunk(
        "doc.rst", code
    )
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_rst_extension_routed_to_loader() -> None:
    """A .rst file goes through the load_rst path, not the markdown engine."""
    src = "Title\n=====\n\nBody text.\n"
    chunks = Chunker(max_chunk_size=200, min_chunk_size=10, size_unit="chars").chunk(
        "x.rst", src
    )
    assert chunks
    assert "".join(c.text for c in chunks) == src


def test_rst_section_underline_extracted() -> None:
    text = "Intro\n=====\n\nbody\n\nSection\n-------\n"
    headings = _extract_section_headings(text)
    assert "Intro" in headings
    assert "Section" in headings


def test_rst_underline_too_short_ignored() -> None:
    text = "LongTitle\n==\n"
    headings = _extract_section_headings(text)
    assert headings == []


def test_rst_code_block_directive_marks_code_segment() -> None:
    src = ".. code-block:: python\n\n    x = 1\n    y = 2\n\nrest of doc.\n"
    doc = load_rst(src)
    code_segs = [s for s in doc.segments if s.kind == "code"]
    assert code_segs
    assert code_segs[0].metadata.get("rst_directive") == "code-block"
    assert code_segs[0].metadata.get("rst_language") == "python"


def test_rst_literalinclude_directive_recognised() -> None:
    src = ".. literalinclude:: foo.py\n    :language: python\n\nbody.\n"
    doc = load_rst(src)
    directives = [s.metadata.get("rst_directive") for s in doc.segments if s.kind == "code"]
    assert "literalinclude" in directives


def test_rst_directive_helper_returns_all_directives(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sample.rst").read_text(encoding="utf-8")
    directives = {name for name, _ in detect_rst_directives(code)}
    assert {"code-block", "note", "warning", "toctree"} <= directives


def test_rst_empty_input_returns_empty_doc() -> None:
    doc = load_rst("")
    assert doc.text == ""
    assert doc.segments == ()

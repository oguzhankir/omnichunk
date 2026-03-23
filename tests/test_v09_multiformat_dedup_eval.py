from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from omnichunk import Chunker, chunk_from_dict, dedup_chunks, evaluate_chunks
from omnichunk.formats.ipynb import load_ipynb
from omnichunk.formats.tex import load_latex
from omnichunk.serialization import chunk_to_dict
from omnichunk.types import ByteRange, Chunk, ChunkContext, ContentType, LineRange

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_ipynb_loader_segments() -> None:
    raw = (_FIXTURES / "sample_v09.ipynb").read_text(encoding="utf-8")
    loaded = load_ipynb(raw)
    assert "Title" in loaded.text
    assert "print(1)" in loaded.text
    assert loaded.format_name == "ipynb"
    kinds = [s.kind for s in loaded.segments]
    assert "prose" in kinds and "code" in kinds


def test_ipynb_byte_reconstruction() -> None:
    path = _FIXTURES / "sample_v09.ipynb"
    chunker = Chunker(max_chunk_size=500, size_unit="chars")
    chunks = chunker.chunk_file(str(path))
    loaded = load_ipynb(path.read_text(encoding="utf-8"))
    raw = loaded.text.encode("utf-8")
    for ch in chunks:
        got = raw[ch.byte_range.start : ch.byte_range.end].decode("utf-8")
        assert got == ch.text


def test_tex_loader_listing() -> None:
    raw = (_FIXTURES / "sample_v09.tex").read_text(encoding="utf-8")
    loaded = load_latex(raw)
    assert "\\section" in loaded.text
    code_seg = [s for s in loaded.segments if s.kind == "code"]
    assert code_seg
    assert "lstlisting" in code_seg[0].metadata.get("latex_env", "")


def test_tex_chunk_reconstruction() -> None:
    path = _FIXTURES / "sample_v09.tex"
    chunker = Chunker(max_chunk_size=500, size_unit="chars")
    chunks = chunker.chunk_file(str(path))
    loaded = load_latex(path.read_text(encoding="utf-8"))
    raw = loaded.text.encode("utf-8")
    for ch in chunks:
        got = raw[ch.byte_range.start : ch.byte_range.end].decode("utf-8")
        assert got == ch.text


def test_dedup_exact() -> None:
    chunker = Chunker(max_chunk_size=100, size_unit="chars")
    chunks = chunker.chunk("a.py", "x = 1\ny = 2\n")
    duped = [replace(c, index=i) for i, c in enumerate(list(chunks) + list(chunks))]
    unique, dup_map = dedup_chunks(duped, method="exact")
    assert len(unique) < len(duped)
    assert dup_map


def test_dedup_minhash_identical_text() -> None:
    text = "def x():\n    return 1\n"
    raw = text.encode("utf-8")
    nws = sum(1 for c in text if not c.isspace())
    chunks: list[Chunk] = []
    for i in range(15):
        ctx = ChunkContext(filepath="a.py", language="python", content_type=ContentType.CODE)
        chunks.append(
            Chunk(
                text=text,
                contextualized_text=text,
                byte_range=ByteRange(0, len(raw)),
                line_range=LineRange(0, 1),
                index=i,
                total_chunks=-1,
                context=ctx,
                char_count=len(text),
                nws_count=nws,
            )
        )
    unique, dup_map = dedup_chunks(chunks, method="minhash", threshold=0.85)
    assert len(unique) == 1
    assert len(dup_map) == 14


def test_eval_reconstruction_and_source() -> None:
    src = "alpha beta gamma.\n"
    chunker = Chunker(max_chunk_size=80, size_unit="chars")
    chunks = chunker.chunk("t.txt", src)
    report = evaluate_chunks(chunks, source=src, metrics=("reconstruction", "density"))
    assert report.aggregate.get("reconstruction") == 1.0
    assert report.aggregate.get("density") is not None


def test_chunk_from_dict_roundtrip() -> None:
    chunker = Chunker(max_chunk_size=100, size_unit="chars")
    chunks = chunker.chunk("z.py", "def f():\n    return 0\n")
    for c in chunks:
        d = chunk_to_dict(c)
        back = chunk_from_dict(d)
        assert back.text == c.text
        assert back.byte_range.start == c.byte_range.start


def test_pdf_loader_smoke() -> None:
    try:
        from io import BytesIO

        from pypdf import PdfWriter
    except ImportError:
        pytest.skip("pypdf not installed")

    from omnichunk.formats.pdf import load_pdf_bytes

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)
    loaded = load_pdf_bytes(buf.getvalue())
    assert loaded.format_name == "pdf"

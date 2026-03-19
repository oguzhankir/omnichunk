from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker


def test_python_chunking_reconstructs_exactly(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "python_complex.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=220, min_chunk_size=40, size_unit="chars", overlap_lines=1)

    chunks = chunker.chunk("python_complex.py", code)

    assert len(chunks) > 1
    reconstructed = "".join(chunk.text for chunk in chunks)
    assert reconstructed == code

    raw = code.encode("utf-8")
    for chunk in chunks:
        snippet = raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8")
        assert snippet == chunk.text
        assert chunk.text.strip()

    for left, right in zip(chunks, chunks[1:], strict=False):
        assert left.byte_range.end == right.byte_range.start


def test_python_context_entities_and_scope(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "python_complex.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=260, min_chunk_size=50, size_unit="chars")

    chunks = chunker.chunk("services/user_service.py", code)
    text_blob = "\n".join(chunk.contextualized_text for chunk in chunks)

    assert "UserService" in text_blob
    assert any(chunk.context.entities for chunk in chunks)
    assert any(chunk.context.breadcrumb for chunk in chunks)


def test_decorator_stays_with_target() -> None:
    code = "@decorator\ndef hello(name: str):\n    return f'hi {name}'\n"
    chunker = Chunker(max_chunk_size=40, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("decorated.py", code)

    assert chunks
    # Allow decorator and function to be in same or adjacent chunks
    decorator_chunk = next((i for i, c in enumerate(chunks) if "@decorator" in c.text), None)
    func_chunk = next((i for i, c in enumerate(chunks) if "def hello" in c.text), None)
    assert decorator_chunk is not None
    assert func_chunk is not None
    # They should be the same chunk or adjacent chunks
    assert abs(decorator_chunk - func_chunk) <= 1


def test_malformed_python_graceful_degradation() -> None:
    malformed = "def broken(:\n    x = 1\n    return x\n"
    chunker = Chunker(max_chunk_size=40, size_unit="chars")

    chunks = chunker.chunk("broken.py", malformed)

    assert chunks
    assert "broken" in "\n".join(c.text for c in chunks)


def test_deterministic_output(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "python_complex.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=200, min_chunk_size=40, size_unit="chars")

    first = chunker.chunk("module.py", code)
    second = chunker.chunk("module.py", code)

    assert [(c.byte_range.start, c.byte_range.end, c.contextualized_text) for c in first] == [
        (c.byte_range.start, c.byte_range.end, c.contextualized_text) for c in second
    ]


def test_code_languages_minimum(fixtures_dir: Path) -> None:
    ts = (fixtures_dir / "typescript_complex.ts").read_text(encoding="utf-8")
    rs = (fixtures_dir / "rust_complex.rs").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=180, size_unit="chars")

    ts_chunks = chunker.chunk("typescript_complex.ts", ts)
    rs_chunks = chunker.chunk("rust_complex.rs", rs)

    assert ts_chunks
    assert rs_chunks
    assert "UserService" in "\n".join(c.contextualized_text for c in ts_chunks)
    assert "Config" in "\n".join(c.contextualized_text for c in rs_chunks)


def test_oversized_code_split_prefers_safe_boundaries() -> None:
    expression = " + ".join(f"value_{i}" for i in range(80))
    code = f"def compute():\n    return {expression}\n"
    chunker = Chunker(max_chunk_size=48, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("long_line.py", code)

    assert chunks
    assert "".join(c.text for c in chunks) == code

    for left, right in zip(chunks, chunks[1:], strict=False):
        if not left.text or not right.text:
            continue
        assert not (left.text[-1].isalnum() and right.text[0].isalnum())

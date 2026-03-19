from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
from omnichunk.engine.hybrid_engine import HybridEngine
from omnichunk.engine.prose_engine import ProseEngine
from omnichunk.types import ChunkOptions
from omnichunk.types import ContentType
from omnichunk.util.text_index import TextIndex


def test_python_docstring_heavy_uses_hybrid(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "mixed_notebook.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=130, min_chunk_size=30, size_unit="chars")

    chunks = chunker.chunk("mixed_notebook.py", code)

    assert chunks
    assert "".join(c.text for c in chunks) == code
    assert any(c.context.content_type in {ContentType.PROSE, ContentType.CODE} for c in chunks)


def test_cell_marker_hybrid_split() -> None:
    content = '# %% [markdown]\n"""\n# Intro\n"""\n# %%\ndef run():\n    return 1\n'
    chunker = Chunker(max_chunk_size=60, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("cells.py", content)

    assert chunks
    assert "".join(c.text for c in chunks) == content
    assert any("# Intro" in c.text for c in chunks)
    assert any("def run" in c.text for c in chunks)


def test_hybrid_engine_reuses_precomputed_segment_indices(monkeypatch) -> None:
    content = '# %% [markdown]\n"""\n# Intro\n"""\n# %%\ndef run():\n    return 1\n'
    engine = HybridEngine()
    captured: list[ChunkOptions] = []

    def _capture_code(filepath: str, text: str, options: ChunkOptions):
        captured.append(options)
        return iter(())

    def _capture_prose(filepath: str, text: str, options: ChunkOptions):
        captured.append(options)
        return iter(())

    monkeypatch.setattr(engine._code_engine, "stream", _capture_code)
    monkeypatch.setattr(engine._prose_engine, "stream", _capture_prose)

    options = ChunkOptions(
        language="python",
        content_type=ContentType.HYBRID,
        _precomputed_text_index=TextIndex(content),
    )

    chunks = engine.chunk("cells.py", content, options)

    assert chunks == []
    assert len(captured) == 2
    assert all(isinstance(item._precomputed_text_index, TextIndex) for item in captured)
    assert all(item._precomputed_nws_cumsum is not None for item in captured)


def test_prose_engine_reuses_precomputed_indices_for_markdown_fence_delegation(
    monkeypatch,
) -> None:
    content = "```python\ndef run():\n    return 1\n```\n"
    engine = ProseEngine()
    captured: list[ChunkOptions] = []

    def _capture_code(filepath: str, text: str, options: ChunkOptions):
        captured.append(options)
        return iter(())

    monkeypatch.setattr(engine._code_engine, "stream", _capture_code)

    chunks = engine.chunk(
        "doc.md",
        content,
        ChunkOptions(
            language="markdown",
            content_type=ContentType.PROSE,
            max_chunk_size=40,
            min_chunk_size=10,
            size_unit="chars",
        ),
    )

    assert captured
    assert isinstance(captured[0]._precomputed_text_index, TextIndex)
    assert captured[0]._precomputed_nws_cumsum is not None
    assert "".join(chunk.text for chunk in chunks) == content

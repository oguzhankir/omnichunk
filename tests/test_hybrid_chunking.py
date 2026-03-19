from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
from omnichunk.types import ContentType


def test_python_docstring_heavy_uses_hybrid(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "mixed_notebook.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=130, min_chunk_size=30, size_unit="chars")

    chunks = chunker.chunk("mixed_notebook.py", code)

    assert chunks
    assert "".join(c.text for c in chunks) == code
    assert any(c.context.content_type in {ContentType.PROSE, ContentType.CODE} for c in chunks)


def test_cell_marker_hybrid_split() -> None:
    content = (
        "# %% [markdown]\n\"\"\"\n# Intro\n\"\"\"\n"
        "# %%\n"
        "def run():\n    return 1\n"
    )
    chunker = Chunker(max_chunk_size=60, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("cells.py", content)

    assert chunks
    assert "".join(c.text for c in chunks) == content
    assert any("# Intro" in c.text for c in chunks)
    assert any("def run" in c.text for c in chunks)

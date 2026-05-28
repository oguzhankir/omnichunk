from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
from omnichunk.formats.ipynb import load_ipynb


def _fixture(fixtures_dir: Path) -> str:
    return (fixtures_dir / "notebook_with_outputs.ipynb").read_text(encoding="utf-8")


def test_ipynb_default_excludes_outputs(fixtures_dir: Path) -> None:
    raw = _fixture(fixtures_dir)
    doc = load_ipynb(raw)
    assert "[output]" not in doc.text
    assert "ZeroDivisionError" not in doc.text


def test_ipynb_include_outputs_true_appends_outputs(fixtures_dir: Path) -> None:
    raw = _fixture(fixtures_dir)
    doc = load_ipynb(raw, include_outputs=True)
    assert "[output]" in doc.text
    assert "ZeroDivisionError" in doc.text


def test_ipynb_empty_code_cell_produces_no_segment(fixtures_dir: Path) -> None:
    raw = _fixture(fixtures_dir)
    doc = load_ipynb(raw)
    # Fixture has one code cell with source == [] — it must not contribute
    # a code-kind segment.
    code_segments = [s for s in doc.segments if s.metadata.get("cell_type") == "code"]
    # Only the first two non-empty code cells + the 1/0 cell = 3 code segments
    assert len(code_segments) == 3


def test_ipynb_cell_metadata_tags_surface_in_segments(fixtures_dir: Path) -> None:
    raw = _fixture(fixtures_dir)
    doc = load_ipynb(raw)
    md_segs = [s for s in doc.segments if s.metadata.get("cell_type") == "markdown"]
    assert md_segs
    assert md_segs[0].metadata.get("tags") == ["intro"]
    code_with_tag = next(
        s
        for s in doc.segments
        if s.metadata.get("cell_type") == "code" and s.metadata.get("tags") == ["important"]
    )
    assert code_with_tag.metadata.get("collapsed") is False


def test_ipynb_raw_cell_is_prose() -> None:
    nb = {
        "cells": [{"cell_type": "raw", "metadata": {}, "source": ["raw text"]}],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    import json as _json

    doc = load_ipynb(_json.dumps(nb))
    raw_segs = [s for s in doc.segments if s.metadata.get("cell_type") == "raw"]
    assert raw_segs
    assert raw_segs[0].kind == "prose"


def test_ipynb_nbformat_v4_minor_5_parses() -> None:
    nb = {
        "cells": [
            {"cell_type": "code", "metadata": {"id": "abc123"}, "source": ["1+1"], "outputs": []}
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    import json as _json

    doc = load_ipynb(_json.dumps(nb))
    assert doc.text.strip() == "1+1"
    assert doc.segments[0].metadata.get("id") == "abc123"


def test_ipynb_chunker_flag_default_excludes_outputs(fixtures_dir: Path) -> None:
    raw = _fixture(fixtures_dir)
    chunks = Chunker().chunk("nb.ipynb", raw)
    full = "".join(c.text for c in chunks)
    assert "[output]" not in full
    assert "ZeroDivisionError" not in full


def test_ipynb_chunker_include_notebook_outputs_true_includes_outputs(
    fixtures_dir: Path,
) -> None:
    raw = _fixture(fixtures_dir)
    chunks = Chunker(include_notebook_outputs=True).chunk("nb.ipynb", raw)
    full = "".join(c.text for c in chunks)
    assert "[output]" in full

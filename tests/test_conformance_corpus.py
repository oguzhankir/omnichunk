"""Frozen, licensed inputs test cross-engine public output contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omnichunk import Chunker, chunk_from_dict
from omnichunk.formats import load_ipynb
from omnichunk.serialization import chunk_to_dict

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "benchmarks/corpus.json").read_text())


@pytest.mark.parametrize("entry", MANIFEST["entries"], ids=lambda e: Path(e["path"]).name)
def test_frozen_corpus_conforms(entry):
    path = ROOT / entry["path"]
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    source = raw.decode("utf-8")
    canonical = load_ipynb(source).text if path.suffix == ".ipynb" else source
    engine = Chunker(max_chunk_size=128, coverage_policy="lossless")
    first = engine.chunk(str(path), source)
    second = engine.chunk(str(path), source)
    assert first == second
    assert "".join(c.text for c in first) == canonical
    for c in first:
        assert canonical.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text
        assert len(c.contextualized_text) <= 128
        assert chunk_from_dict(chunk_to_dict(c)) == c
        for entity in [*c.context.entities, *c.context.scope]:
            if entity.byte_range is not None:
                assert (
                    0 <= entity.byte_range.start <= entity.byte_range.end <= len(canonical.encode())
                )


def test_deep_ast_windowing_is_iterative():
    from omnichunk.sizing.nws import preprocess_nws_cumsum
    from omnichunk.windowing.greedy import RangeNode, greedy_assign_windows

    source = "alpha beta gamma"
    node = RangeNode(0, len(source))
    for _ in range(2000):
        node = RangeNode(0, len(source), (node,))
    result = list(
        greedy_assign_windows([node], code=source, cumsum=preprocess_nws_cumsum(source), max_size=4)
    )
    assert result

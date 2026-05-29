from __future__ import annotations

import importlib.util
import sys
import types

import numpy as np
import pytest

from omnichunk.semantic.embedders import get_local_embedder

_HAVE_ST = importlib.util.find_spec("sentence_transformers") is not None


@pytest.mark.skipif(_HAVE_ST, reason="sentence-transformers is installed")
def test_get_local_embedder_raises_without_extra() -> None:
    with pytest.raises(ImportError, match="sentence-transformers"):
        get_local_embedder()


def test_get_local_embedder_with_mocked_package(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {"constructed_with": None, "encoded": None}

    class _FakeModel:
        def __init__(self, model_name: str) -> None:
            calls["constructed_with"] = model_name

        def encode(self, texts: list[str], convert_to_numpy: bool = True) -> np.ndarray:
            calls["encoded"] = list(texts)
            return np.ones((len(texts), 3), dtype=np.float64)

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embed = get_local_embedder("all-MiniLM-L6-v2")
    # Lazy: constructing the embedder must NOT build the model yet.
    assert calls["constructed_with"] is None

    out = embed(["hello", "world"])
    assert calls["constructed_with"] == "all-MiniLM-L6-v2"
    assert calls["encoded"] == ["hello", "world"]
    assert out.shape == (2, 3)


def test_local_embedder_caches_model(monkeypatch: pytest.MonkeyPatch) -> None:
    construct_count = {"n": 0}

    class _FakeModel:
        def __init__(self, model_name: str) -> None:
            construct_count["n"] += 1

        def encode(self, texts: list[str], convert_to_numpy: bool = True) -> np.ndarray:
            return np.zeros((len(texts), 2), dtype=np.float64)

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embed = get_local_embedder()
    embed(["a"])
    embed(["b"])
    embed(["c"])
    # Model constructed exactly once and reused across calls.
    assert construct_count["n"] == 1


def test_mocked_embedder_integrates_with_semantic_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omnichunk import Chunker

    rng = np.random.default_rng(0)

    class _FakeModel:
        def __init__(self, model_name: str) -> None:
            pass

        def encode(self, texts: list[str], convert_to_numpy: bool = True) -> np.ndarray:
            return rng.standard_normal((len(texts), 8))

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    embed = get_local_embedder()
    chunker = Chunker(max_chunk_size=120, size_unit="chars")
    text = "Topic one sentence. Topic one again.\n\nTopic two now. Topic two tail."
    chunks = chunker.semantic_chunk("doc.md", text, embed_fn=embed)
    assert chunks
    assert "".join(c.text for c in chunks) == text

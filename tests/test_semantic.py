from __future__ import annotations

import re

import numpy as np
import pytest

from omnichunk import Chunker, ChunkOptions
from omnichunk.semantic import SemanticSplitter, detect_semantic_boundaries, split_sentences
from omnichunk.sizing.nws import preprocess_nws_cumsum


def test_split_sentences_basic_reconstruction() -> None:
    text = "Hello world. This is a test. Final sentence!"
    sentences = split_sentences(text)
    assert "".join(s for s, _, _ in sentences) == text


def test_split_sentences_empty() -> None:
    sentences = split_sentences("")
    assert len(sentences) == 1
    assert sentences[0][0] == ""


def test_split_sentences_double_newline_split() -> None:
    text = "Para one.\n\nPara two."
    sentences = split_sentences(text)
    assert len(sentences) >= 2
    assert "".join(s for s, _, _ in sentences) == text


def test_split_sentences_custom_fn() -> None:
    def fn(t: str) -> list[str]:
        # Capturing split keeps delimiters so join reconstructs the source.
        return re.split(r"(\|)", t)

    text = "a|b|c"
    sentences = split_sentences(text, splitter_fn=fn)
    assert "".join(s for s, _, _ in sentences) == text


def test_detect_semantic_boundaries_deterministic() -> None:
    sentences = ["First.", "Second.", "Third.", "Fourth.", "Fifth."]

    def embed(texts: list[str]) -> np.ndarray:
        out = []
        for i, _t in enumerate(texts):
            v = np.zeros(4)
            v[i % 4] = 1.0
            out.append(v)
        return np.array(out)

    r1 = detect_semantic_boundaries(sentences, embed_fn=embed)
    r2 = detect_semantic_boundaries(sentences, embed_fn=embed)
    assert r1 == r2


def test_detect_semantic_boundaries_no_embed_call_for_single_sentence() -> None:
    calls = {"n": 0}

    def embed(texts: list[str]) -> np.ndarray:
        calls["n"] += 1
        return np.zeros((len(texts), 4))

    detect_semantic_boundaries(["Only one."], embed_fn=embed)
    assert calls["n"] <= 1


def test_detect_semantic_boundaries_wrong_shape_raises() -> None:
    def bad_embed(texts: list[str]) -> np.ndarray:
        return np.zeros(4)

    with pytest.raises(ValueError):
        detect_semantic_boundaries(["a", "b"], embed_fn=bad_embed)


def test_semantic_splitter_reconstruction() -> None:
    text = (
        "The quick brown fox jumps. "
        "Over the lazy dog today.\n\n"
        "A completely different topic begins here. "
        "More text about the new topic follows."
    )
    rng = np.random.default_rng(42)

    def embed(texts: list[str]) -> np.ndarray:
        return rng.standard_normal((len(texts), 8))

    splitter = SemanticSplitter(embed_fn=embed, window=2, threshold=0.0)
    opts = ChunkOptions(
        max_chunk_size=200,
        size_unit="chars",
        semantic=True,
        semantic_embed_fn=embed,
        semantic_window=2,
        semantic_threshold=0.0,
        _precomputed_nws_cumsum=preprocess_nws_cumsum(text),
    )
    chunks = splitter.split("doc.md", text, opts)
    assert chunks
    assert "".join(c.text for c in chunks) == text
    raw = text.encode("utf-8")
    for ch in chunks:
        assert raw[ch.byte_range.start : ch.byte_range.end].decode("utf-8") == ch.text
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_chunker_semantic_chunk_method() -> None:
    rng = np.random.default_rng(0)
    embed = lambda texts: rng.standard_normal((len(texts), 4))  # noqa: E731
    chunker = Chunker(max_chunk_size=100, size_unit="chars")
    text = "Sentence one. Sentence two.\n\nNew paragraph here. Another sentence."
    chunks = chunker.semantic_chunk("doc.md", text, embed_fn=embed)
    assert chunks
    assert "".join(c.text for c in chunks) == text


def test_semantic_engine_falls_back_for_code() -> None:
    embed = lambda texts: np.eye(len(texts), 4)  # noqa: E731
    chunker = Chunker(
        max_chunk_size=128,
        size_unit="chars",
        semantic=True,
        semantic_embed_fn=embed,
    )
    code = "def foo():\n    return 1\n" * 5
    chunks = chunker.chunk("test.py", code)
    assert chunks
    assert "".join(c.text for c in chunks) == code

from __future__ import annotations

from dataclasses import asdict

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from omnichunk import Chunker

_HYP_SETTINGS = settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

_ENCODABLE_CHAR = st.characters(blacklist_categories=["Cs"])
_SURROGATE_CHAR = st.characters(min_codepoint=0xD800, max_codepoint=0xDFFF)
_SPECIAL_CHAR = st.sampled_from(
    ["\x00", "\ufeff", "\n", "\r", "\t", " ", "\u2003", "\u2028", "\u2029"]
)
_MIXED_ALPHABET = st.one_of(_ENCODABLE_CHAR, _SURROGATE_CHAR, _SPECIAL_CHAR)
_ASCII_ALPHABET = st.characters(min_codepoint=0, max_codepoint=0x7F)

_SMALL_TEXT = st.text(alphabet=_MIXED_ALPHABET, min_size=0, max_size=3000)
_LARGE_TEXT = st.text(alphabet=_MIXED_ALPHABET, min_size=3001, max_size=50000)
_STRESS_TEXT = st.one_of(_SMALL_TEXT, _SMALL_TEXT, _SMALL_TEXT, _SMALL_TEXT, _LARGE_TEXT)
_ASCII_STRESS_TEXT = st.text(alphabet=_ASCII_ALPHABET, min_size=0, max_size=50000)
_JSON_TEXT = st.text(alphabet=_MIXED_ALPHABET, min_size=0, max_size=4000)


def _chunk_snapshot(filepath: str, text: str, chunker: Chunker) -> list[dict]:
    return [asdict(c) for c in chunker.chunk(filepath, text)]


def _assert_invariants(filepath: str, text: str, chunker: Chunker) -> None:
    # Inputs containing lone surrogates are intentionally generated to verify
    # deterministic behavior when UTF-8 encoding is impossible.
    try:
        source_bytes = text.encode("utf-8")
    except UnicodeEncodeError:
        with pytest.raises(UnicodeEncodeError):
            _chunk_snapshot(filepath, text, chunker)
        with pytest.raises(UnicodeEncodeError):
            _chunk_snapshot(filepath, text, chunker)
        return

    chunks_a = chunker.chunk(filepath, text)
    chunks_b = chunker.chunk(filepath, text)

    # 4) Determinism: two runs must be identical.
    assert [asdict(c) for c in chunks_a] == [asdict(c) for c in chunks_b]

    # 2) Contiguity for adjacent chunks.
    for i in range(len(chunks_a) - 1):
        assert chunks_a[i].byte_range.end == chunks_a[i + 1].byte_range.start

    for c in chunks_a:
        # 1) Byte-slice reconstruction must match chunk text.
        assert source_bytes[c.byte_range.start : c.byte_range.end].decode("utf-8") == c.text
        # 3) No empty / whitespace-only chunks.
        assert c.text != ""
        assert c.text.strip() != ""


@_HYP_SETTINGS
@given(body=_ASCII_STRESS_TEXT)
def test_hypothesis_invariants_python_path(body: str) -> None:
    text = f"def fn(x):\n    return x\n\n{body}"
    chunker = Chunker(max_chunk_size=320, min_chunk_size=12, size_unit="chars")
    _assert_invariants("fuzz.py", text, chunker)


@_HYP_SETTINGS
@given(body=_STRESS_TEXT)
def test_hypothesis_invariants_markdown_path(body: str) -> None:
    text = f"# Title\n\n## Subtitle\n\n{body}\n\n- a\n- b\n"
    chunker = Chunker(max_chunk_size=320, min_chunk_size=12, size_unit="chars")
    _assert_invariants("fuzz.md", text, chunker)


@_HYP_SETTINGS
@given(body=_STRESS_TEXT)
def test_hypothesis_invariants_plaintext_path(body: str) -> None:
    text = f"{body}\n\nplain paragraph\n\nanother paragraph"
    chunker = Chunker(max_chunk_size=280, min_chunk_size=8, size_unit="chars")
    _assert_invariants("fuzz.txt", text, chunker)


@_HYP_SETTINGS
@given(body=_JSON_TEXT)
def test_hypothesis_invariants_json_path(body: str) -> None:
    safe = body.replace('"', '\\"').replace("\n", " ")
    text = '{"title":"fuzz","payload":"' + safe + '","ok":true}'
    chunker = Chunker(max_chunk_size=300, min_chunk_size=10, size_unit="chars")
    _assert_invariants("fuzz.json", text, chunker)


@_HYP_SETTINGS
@given(body=_STRESS_TEXT)
def test_hypothesis_invariants_html_path(body: str) -> None:
    text = "<html><body><h1>Title</h1><p>" + body + "</p><div>tail</div></body></html>"
    chunker = Chunker(max_chunk_size=300, min_chunk_size=10, size_unit="chars")
    _assert_invariants("fuzz.html", text, chunker)


@_HYP_SETTINGS
@given(body=_STRESS_TEXT)
def test_hypothesis_invariants_toml_path(body: str) -> None:
    safe = body.replace("\n", " ").replace('"', '\\"')
    text = '[meta]\nname = "fuzz"\ntext = "' + safe + '"\n'
    chunker = Chunker(max_chunk_size=260, min_chunk_size=8, size_unit="chars")
    _assert_invariants("fuzz.toml", text, chunker)


@_HYP_SETTINGS
@given(body=_STRESS_TEXT)
def test_hypothesis_invariants_yaml_path(body: str) -> None:
    safe = body.replace("\n", " ")
    text = f"title: fuzz\nbody: |\n  {safe}\nitems:\n  - a\n  - b\n"
    chunker = Chunker(max_chunk_size=260, min_chunk_size=8, size_unit="chars")
    _assert_invariants("fuzz.yaml", text, chunker)


@_HYP_SETTINGS
@given(body=_STRESS_TEXT)
def test_hypothesis_invariants_hybrid_cells_python_path(body: str) -> None:
    text = '# %% [markdown]\n"""\\n# Intro\\n"""\\n# %%\nprint("x")\n' + body
    chunker = Chunker(max_chunk_size=300, min_chunk_size=10, size_unit="chars")
    _assert_invariants("fuzz_cells.py", text, chunker)

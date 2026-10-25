"""Every measured chunker uses source slices and the same explicit budget."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from benchmarks.retrieval import adapters

SOURCE = "## heading\n\n資料😀 beta repeated\n\n資料😀 beta repeated\n\nTail text."


@pytest.mark.parametrize("tool", ["fixed", "omnichunk"])
@pytest.mark.parametrize("unit", ["chars", "tokens"])
def test_builtin_adapters_preserve_unicode_and_obey_actual_counter(tool, unit):
    counter = len if unit == "chars" else lambda text: len(text.encode("utf-8"))
    chunks = adapters.split_document(tool, "doc", "doc.md", SOURCE, 24, counter, unit)
    assert chunks
    assert "".join(chunk.text for chunk in chunks) == SOURCE
    raw = SOURCE.encode()
    for chunk in chunks:
        assert raw[chunk.start : chunk.end].decode() == chunk.text
        assert counter(chunk.text) <= 24
    assert len({chunk.passage_id for chunk in chunks}) == len(chunks)
    assert chunks == adapters.split_document(tool, "doc", "doc.md", SOURCE, 24, counter, unit)
    assert (
        chunks[0].passage_id
        != adapters.split_document(tool, "other-doc", "doc.md", SOURCE, 24, counter, unit)[
            0
        ].passage_id
    )


@pytest.mark.parametrize(
    "tool,module",
    [
        ("semchunk", "semchunk"),
        ("langchain", "langchain_text_splitters"),
        ("semantic-text-splitter", "semantic_text_splitter"),
        ("llamaindex", "llama_index.core.node_parser"),
        ("chonkie", "chonkie"),
    ],
)
@pytest.mark.parametrize("unit", ["chars", "tokens"])
def test_installed_optional_adapters_preserve_exact_source_slices(tool, module, unit):
    pytest.importorskip(module)
    counter = len if unit == "chars" else lambda text: len(text.encode("utf-8"))
    if tool == "chonkie" and unit == "tokens":
        with pytest.raises(adapters.AdapterUnavailable, match="encode/decode"):
            adapters.split_document(tool, "doc", "doc.md", SOURCE, 24, counter, unit)
        return
    chunks = adapters.split_document(tool, "doc", "doc.md", SOURCE, 24, counter, unit)
    assert chunks
    raw = SOURCE.encode()
    assert all(raw[chunk.start : chunk.end].decode() == chunk.text for chunk in chunks)
    assert all(counter(chunk.text) <= 24 for chunk in chunks)
    assert all(a.end <= b.start for a, b in zip(chunks, chunks[1:]))


def test_repeated_outputs_map_to_distinct_utf8_source_occurrences(monkeypatch):
    monkeypatch.setattr(adapters, "_split_texts", lambda *_: ["資料😀", "資料😀"])
    chunks = adapters.split_document("fixed", "doc", "d.txt", "資料😀 資料😀", 20, len, "chars")
    assert [(chunk.start, chunk.end) for chunk in chunks] == [(0, 10), (11, 21)]
    assert chunks[0].passage_id != chunks[1].passage_id


@pytest.mark.parametrize(
    "pieces,error",
    [
        (["wrong"], "source slice"),
        (["def", "abc"], "source slice"),
        (["abc", "bc"], "source slice"),
        (["abcdef"], "budget"),
        ([42], "strings"),
    ],
)
def test_adapter_rewrites_reordering_overlap_and_overflow_fail(monkeypatch, pieces, error):
    monkeypatch.setattr(adapters, "_split_texts", lambda *_: pieces)
    with pytest.raises(ValueError, match=error):
        adapters.split_document("fixed", "doc", "d.txt", "abcdef", 5, len, "chars")


def test_adapter_failure_is_not_misreported_as_unavailable(monkeypatch):
    def fail(*args):
        raise RuntimeError("backend failure")

    monkeypatch.setattr(adapters, "_split_texts", fail)
    with pytest.raises(RuntimeError, match="backend failure"):
        adapters.split_document("semchunk", "doc", "d.txt", "abcdef", 5, len, "chars")


@pytest.mark.parametrize(
    "source,pieces",
    [
        ("important context answer trailing evidence", ["answer"]),
        ("missing answer", ["answer"]),
        ("first missing last", ["first", "last"]),
        ("answer missing", ["answer"]),
        ("資料😀", []),
        ("資料😀", [""]),
        ("資料 missing 😀", ["資料", "😀"]),
    ],
)
def test_adapter_cannot_silently_drop_nonwhitespace(source, pieces, monkeypatch):
    monkeypatch.setattr(adapters, "_split_texts", lambda *_: iter(pieces))
    with pytest.raises(ValueError, match="drops non-whitespace"):
        adapters.split_document("fixed", "doc", "d.txt", source, 100, len, "chars")


@pytest.mark.parametrize(
    "source,pieces",
    [(" \t資料\n\u2003😀\r\n", ["資料", "😀"]), (" \t\n\u2003", []), ("", [])],
)
def test_adapter_may_omit_only_whitespace(source, pieces, monkeypatch):
    monkeypatch.setattr(adapters, "_split_texts", lambda *_: iter(pieces))
    chunks = adapters.split_document("fixed", "doc", "d.txt", source, 100, len, "chars")
    assert [chunk.text for chunk in chunks] == pieces
    raw = source.encode()
    assert all(raw[c.start : c.end].decode() == c.text for c in chunks)


def test_absent_tool_is_unavailable_but_broken_transitive_import_is_error(monkeypatch):
    def absent(name):
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(importlib, "import_module", absent)
    with pytest.raises(adapters.AdapterUnavailable):
        adapters.split_document("semchunk", "doc", "d.txt", "abc", 5, len, "chars")

    def broken(name):
        raise ModuleNotFoundError(name="internal_backend")

    monkeypatch.setattr(importlib, "import_module", broken)
    with pytest.raises(ModuleNotFoundError) as failure:
        adapters.split_document("semchunk", "doc", "d.txt", "abc", 5, len, "chars")
    assert not isinstance(failure.value, adapters.AdapterUnavailable)


def test_missing_verified_api_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        adapters, "_optional_module", lambda _: SimpleNamespace(__name__="semchunk")
    )
    with pytest.raises(adapters.AdapterUnavailable, match="verified chunkerify"):
        adapters.split_document("semchunk", "doc", "d.txt", "abc", 5, len, "chars")


def test_chonkie_count_only_token_comparison_is_explicitly_unavailable():
    with pytest.raises(adapters.AdapterUnavailable, match="encode/decode"):
        adapters.split_document("chonkie", "doc", "d.txt", "abc", 5, len, "tokens")


@pytest.mark.parametrize("capacity", [0, -1, True, 3.5])
def test_invalid_capacity_is_rejected(capacity):
    with pytest.raises(ValueError, match="capacity"):
        adapters.split_document("fixed", "doc", "d.txt", "abc", capacity, len, "chars")


def test_fixed_counter_that_cannot_fit_any_character_fails():
    with pytest.raises(ValueError, match="Unicode character"):
        adapters.split_document("fixed", "doc", "d.txt", "資料😀", 1, lambda _: 2, "tokens")


@pytest.mark.parametrize("tool", ["fixed", "omnichunk"])
def test_empty_input_has_no_passages(tool):
    assert adapters.split_document(tool, "doc", "d.txt", "", 5, len, "chars") == []

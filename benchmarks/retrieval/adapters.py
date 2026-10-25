"""Budget-equivalent, zero-overlap adapters for the retrieval benchmark.

Only exact source slices are accepted. Optional integrations are imported lazily;
an unavailable dependency/API is distinct from invalid output or a runtime error.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omnichunk import Chunker
from omnichunk.sizing.counter import find_fitting_prefix

TOOLS = (
    "omnichunk",
    "fixed",
    "semchunk",
    "langchain",
    "semantic-text-splitter",
    "chonkie",
    "llamaindex",
)
TOOL_DISTRIBUTIONS = {
    "omnichunk": "omnichunk",
    "fixed": None,
    "semchunk": "semchunk",
    "langchain": "langchain-text-splitters",
    "semantic-text-splitter": "semantic-text-splitter",
    "chonkie": "chonkie",
    "llamaindex": "llama-index-core",
}


class AdapterUnavailable(ImportError):
    """The optional dependency or a verified equivalent API is unavailable."""


@dataclass(frozen=True)
class Passage:
    passage_id: str
    source_id: str
    start: int
    end: int
    text: str


def _optional_module(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        # Do not hide a broken optional installation with a missing internal
        # dependency. That is a failed candidate, rather than an absent tool.
        if exc.name == name or (exc.name and name.startswith(exc.name + ".")):
            raise AdapterUnavailable(f"Install the optional {name} dependency") from exc
        raise


def _required_attribute(module: Any, name: str) -> Any:
    value = getattr(module, name, None)
    if not callable(value):
        raise AdapterUnavailable(f"{module.__name__} lacks the verified {name} API")
    return value


def _requires_parameters(function: Any, *names: str) -> None:
    parameters = inspect.signature(function).parameters
    if any(name not in parameters for name in names):
        raise AdapterUnavailable(f"{function} lacks the verified parameters: {', '.join(names)}")


def _fixed(text: str, capacity: int, counter: Callable[[str], int]) -> Iterable[str]:
    cursor = 0
    while cursor < len(text):
        end = find_fitting_prefix(text, cursor, len(text), capacity, counter)
        if end == cursor:
            raise ValueError("A Unicode character cannot fit the shared budget")
        yield text[cursor:end]
        cursor = end


def _split_texts(
    tool: str,
    path: str,
    text: str,
    capacity: int,
    counter: Callable[[str], int],
    unit: str,
) -> Iterable[str]:
    if tool == "fixed":
        return _fixed(text, capacity, counter)
    if tool == "semchunk":
        factory = _required_attribute(_optional_module("semchunk"), "chunkerify")
        _requires_parameters(factory, "chunk_size")
        return factory(counter, chunk_size=capacity)(text, overlap=0)
    if tool == "langchain":
        splitter = _required_attribute(
            _optional_module("langchain_text_splitters"), "RecursiveCharacterTextSplitter"
        )
        return splitter(
            chunk_size=capacity,
            chunk_overlap=0,
            length_function=counter,
            separators=["\n\n", "\n", " ", ""],
            strip_whitespace=False,
        ).split_text(text)
    if tool == "semantic-text-splitter":
        module = _optional_module("semantic_text_splitter")
        name = (
            "MarkdownSplitter"
            if Path(path).suffix.lower() in {".md", ".markdown"}
            else "TextSplitter"
        )
        splitter_type = _required_attribute(module, name)
        # A callback keeps character and token experiments on exactly the same
        # counter, including custom counters used in conformance checks.
        factory = _required_attribute(splitter_type, "from_callback")
        return factory(counter, capacity, overlap=0, trim=False).chunks(text)
    if tool == "chonkie":
        if unit != "chars" or counter is not len:
            raise AdapterUnavailable(
                "Chonkie recursive token splitting requires tokenizer encode/decode; "
                "a count-only callback cannot establish equivalent token behavior"
            )
        splitter = _required_attribute(_optional_module("chonkie"), "RecursiveChunker")
        _requires_parameters(splitter, "tokenizer", "chunk_size", "min_characters_per_chunk")
        return (
            chunk.text
            for chunk in splitter(
                tokenizer="character", chunk_size=capacity, min_characters_per_chunk=1
            ).chunk(text)
        )
    if tool == "llamaindex":
        splitter = _required_attribute(
            _optional_module("llama_index.core.node_parser"), "TokenTextSplitter"
        )
        _requires_parameters(splitter, "tokenizer", "keep_whitespaces")
        # TokenTextSplitter only reads len(tokenizer(text)). A range exposes the
        # exact shared count without allocating fake model token sequences.
        return splitter(
            chunk_size=capacity,
            chunk_overlap=0,
            tokenizer=lambda value: range(counter(value)),
            keep_whitespaces=True,
            include_metadata=False,
            include_prev_next_rel=False,
        ).split_text(text)
    raise ValueError(f"Unknown retrieval adapter: {tool}")


def _passage(source_id: str, start: int, end: int, text: str) -> Passage:
    digest = hashlib.sha256(f"{source_id}\0{start}\0{end}\0{text}".encode()).hexdigest()
    return Passage(digest, source_id, start, end, text)


def _normalize(
    source_id: str, text: str, pieces: Iterable[str], capacity: int, counter: Callable[[str], int]
) -> list[Passage]:
    cursor = 0
    result = []
    for piece in pieces:
        if not isinstance(piece, str):
            raise ValueError("Adapter output must contain strings")
        if not piece:
            continue
        if counter(piece) > capacity:
            raise ValueError("Adapter output exceeds the shared payload budget")
        start = text.find(piece, cursor)
        if start < 0:
            raise ValueError("Adapter output is not an ordered, non-overlapping source slice")
        if text[cursor:start].strip():
            raise ValueError("Adapter source slice drops non-whitespace source text")
        end = start + len(piece)
        result.append(
            _passage(source_id, len(text[:start].encode()), len(text[:end].encode()), piece)
        )
        cursor = end
    if text[cursor:].strip():
        raise ValueError("Adapter output drops non-whitespace source text at the end")
    return result


def split_document(
    tool: str,
    source_id: str,
    path: str,
    text: str,
    capacity: int,
    counter: Callable[[str], int],
    unit: str,
) -> list[Passage]:
    """Return validated UTF-8 passages with the shared capacity and no overlap.

    Adapters may omit whitespace. They may not rewrite text, add context, exceed
    the measured budget or reuse a source span. Dependency/API absence raises
    ``AdapterUnavailable``; malformed output and runtime failures remain errors.
    """
    if tool not in TOOLS:
        raise ValueError(f"Unknown retrieval adapter: {tool}")
    if unit not in {"chars", "tokens"}:
        raise ValueError("unit must be 'chars' or 'tokens'")
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")
    if not source_id:
        raise ValueError("source_id must be nonempty")
    if tool == "omnichunk":
        chunks = Chunker(
            max_chunk_size=capacity,
            min_chunk_size=0,
            size_unit=unit,
            tokenizer=counter if unit == "tokens" else None,
            context_mode="none",
            coverage_policy="lossless",
            overlap=None,
            overlap_lines=0,
            nws_backend="python",
        ).chunk(path, text)
        pieces = [chunk.text for chunk in chunks]
    else:
        pieces = _split_texts(tool, path, text, capacity, counter, unit)
    return _normalize(source_id, text, pieces, capacity, counter)

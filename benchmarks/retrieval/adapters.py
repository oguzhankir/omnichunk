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
from typing import Any, cast

from omnichunk import Chunker
from omnichunk.sizing.counter import find_fitting_prefix

TOOLS = (
    "omnichunk",
    "omnichunk-pack",
    "fixed",
    "semchunk",
    "langchain",
    "langchain-code",
    "semantic-text-splitter",
    "chonkie",
    "chonkie-sentence",
    "llamaindex",
    "llamaindex-sentence",
)
TOOL_DISTRIBUTIONS = {
    "omnichunk": "omnichunk",
    "omnichunk-pack": "omnichunk",
    "fixed": None,
    "semchunk": "semchunk",
    "langchain": "langchain-text-splitters",
    "langchain-code": "langchain-text-splitters",
    "semantic-text-splitter": "semantic-text-splitter",
    "chonkie": "chonkie",
    "chonkie-sentence": "chonkie",
    "llamaindex": "llama-index-core",
    "llamaindex-sentence": "llama-index-core",
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
        return cast(Iterable[str], factory(counter, chunk_size=capacity)(text, overlap=0))
    if tool in {"langchain", "langchain-code"}:
        module = _optional_module("langchain_text_splitters")
        splitter = _required_attribute(module, "RecursiveCharacterTextSplitter")
        if tool == "langchain-code":
            # Select the upstream separator recipe from the input extension.
            # Unknown/plain-text extensions use the generic historical recipe.
            extension_languages = {
                ".py": "python",
                ".js": "js",
                ".jsx": "js",
                ".ts": "ts",
                ".tsx": "ts",
                ".java": "java",
                ".go": "go",
                ".rs": "rust",
                ".c": "c",
                ".h": "c",
                ".cpp": "cpp",
                ".cc": "cpp",
                ".hpp": "cpp",
                ".cs": "csharp",
                ".kt": "kotlin",
                ".rb": "ruby",
                ".php": "php",
                ".swift": "swift",
                ".scala": "scala",
                ".lua": "lua",
                ".hs": "haskell",
                ".ex": "elixir",
                ".exs": "elixir",
                ".md": "markdown",
                ".markdown": "markdown",
                ".html": "html",
                ".tex": "latex",
                ".rst": "rst",
            }
            language = extension_languages.get(Path(path).suffix.lower())
            if language is not None:
                factory = _required_attribute(splitter, "from_language")
                language_type = getattr(module, "Language", None)
                if language_type is None:
                    raise AdapterUnavailable("langchain_text_splitters lacks Language")
                return cast(
                    Iterable[str],
                    factory(
                        language_type(language),
                        chunk_size=capacity,
                        chunk_overlap=0,
                        length_function=counter,
                        strip_whitespace=False,
                    ).split_text(text),
                )
        return cast(
            Iterable[str],
            splitter(
                chunk_size=capacity,
                chunk_overlap=0,
                length_function=counter,
                separators=["\n\n", "\n", " ", ""],
                strip_whitespace=False,
            ).split_text(text),
        )
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
        return cast(Iterable[str], factory(counter, capacity, overlap=0, trim=False).chunks(text))
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
    if tool == "chonkie-sentence":
        splitter = _required_attribute(_optional_module("chonkie"), "SentenceChunker")
        _requires_parameters(
            splitter, "tokenizer", "chunk_size", "chunk_overlap", "min_characters_per_sentence"
        )
        # SentenceChunker supports count-only tokenizers without encode/decode.
        # Oversized single sentences remain conformance failures in _normalize;
        # never silently repair the competitor's output with our own splitter.
        return (
            chunk.text
            for chunk in splitter(
                tokenizer=counter,
                chunk_size=capacity,
                chunk_overlap=0,
                min_characters_per_sentence=1,
            ).chunk(text)
        )
    if tool == "llamaindex":
        splitter = _required_attribute(
            _optional_module("llama_index.core.node_parser"), "TokenTextSplitter"
        )
        _requires_parameters(splitter, "tokenizer", "keep_whitespaces")
        # TokenTextSplitter only reads len(tokenizer(text)). A range exposes the
        # exact shared count without allocating fake model token sequences.
        return cast(
            Iterable[str],
            splitter(
                chunk_size=capacity,
                chunk_overlap=0,
                tokenizer=lambda value: range(counter(value)),
                keep_whitespaces=True,
                include_metadata=False,
                include_prev_next_rel=False,
            ).split_text(text),
        )
    if tool == "llamaindex-sentence":
        splitter = _required_attribute(
            _optional_module("llama_index.core.node_parser"), "SentenceSplitter"
        )
        _requires_parameters(splitter, "tokenizer", "chunk_overlap", "paragraph_separator")
        return cast(
            Iterable[str],
            splitter(
                chunk_size=capacity,
                chunk_overlap=0,
                tokenizer=lambda value: range(counter(value)),
                include_metadata=False,
                include_prev_next_rel=False,
            ).split_text(text),
        )
    raise ValueError(f"Unknown retrieval adapter: {tool}")


def _passage(source_id: str, start: int, end: int, text: str) -> Passage:
    digest = hashlib.sha256(f"{source_id}\0{start}\0{end}\0{text}".encode()).hexdigest()
    return Passage(digest, source_id, start, end, text)


def _normalize(
    source_id: str, text: str, pieces: Iterable[str], capacity: int, counter: Callable[[str], int]
) -> list[Passage]:
    if isinstance(pieces, (str, bytes)):
        raise ValueError("Adapter output must be an iterable of strings, not a single string")
    cursor = 0
    byte_cursor = 0
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
        gap = text[cursor:start]
        if gap.strip():
            raise ValueError("Adapter source slice drops non-whitespace source text")
        end = start + len(piece)
        # Count each source character once. Encoding full prefixes per passage
        # makes validation quadratic and distorts chunker latency on large files.
        byte_start = byte_cursor + len(gap.encode("utf-8"))
        byte_end = byte_start + len(piece.encode("utf-8"))
        result.append(_passage(source_id, byte_start, byte_end, piece))
        cursor = end
        byte_cursor = byte_end
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
    pieces: Iterable[str]
    if tool in {"omnichunk", "omnichunk-pack"}:
        experimental = {"markdown_paragraph_policy": "pack"} if tool == "omnichunk-pack" else {}
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
            **experimental,
        ).chunk(path, text)
        pieces = [chunk.text for chunk in chunks]
    else:
        pieces = _split_texts(tool, path, text, capacity, counter, unit)
    return _normalize(source_id, text, pieces, capacity, counter)

# ruff: noqa: E402
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nltk.corpus import gutenberg

from omnichunk import Chunker


@dataclass(frozen=True)
class RealResult:
    tool: str
    total_texts: int
    total_chars: int
    total_tokens: int
    total_chunks: int
    avg_chunk_tokens: float
    seconds: float
    status: str
    detail: str = ""


def _optional_import(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _gpt4_tokenizer():
    import tiktoken

    return tiktoken.encoding_for_model("gpt-4")


def _run_omnichunk(texts: list[str]) -> RealResult:
    chunker = Chunker()
    total_chunks = 0
    total_tokens = 0
    tokenizer = _gpt4_tokenizer()

    started = perf_counter()
    for text in texts:
        tokens = tokenizer.encode(text)
        total_tokens += len(tokens)
        chunks = chunker.chunk(
            "gutenberg.txt",
            text,
            max_chunk_size=512,
            min_chunk_size=128,
            size_unit="tokens",
        )
        total_chunks += len(chunks)
    elapsed = perf_counter() - started

    total_chars = sum(len(text) for text in texts)
    avg_chunk = total_tokens / total_chunks if total_chunks > 0 else 0.0

    return RealResult(
        tool="omnichunk",
        total_texts=len(texts),
        total_chars=total_chars,
        total_tokens=total_tokens,
        total_chunks=total_chunks,
        avg_chunk_tokens=avg_chunk,
        seconds=elapsed,
        status="ok",
    )


def _run_langchain_recursive(texts: list[str]) -> RealResult:
    module = _optional_import("langchain_text_splitters")
    if module is None:
        module = _optional_import("langchain.text_splitter")
    if module is None:
        raise ImportError("langchain RecursiveCharacterTextSplitter is unavailable")

    splitter_cls = getattr(module, "RecursiveCharacterTextSplitter", None)
    if splitter_cls is None:
        raise ImportError("RecursiveCharacterTextSplitter not found")

    tokenizer = _gpt4_tokenizer()
    splitter = splitter_cls.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=512,
        chunk_overlap=0,
        separators=["\n\n", "\n", " ", ""],
    )

    started = perf_counter()
    total_chunks = 0
    total_tokens = 0
    for text in texts:
        tokens = tokenizer.encode(text)
        total_tokens += len(tokens)
        chunks = splitter.split_text(text)
        total_chunks += len(chunks)
    elapsed = perf_counter() - started

    total_chars = sum(len(text) for text in texts)
    avg_chunk = total_tokens / total_chunks if total_chunks > 0 else 0.0

    return RealResult(
        tool="langchain_recursive",
        total_texts=len(texts),
        total_chars=total_chars,
        total_tokens=total_tokens,
        total_chunks=total_chunks,
        avg_chunk_tokens=avg_chunk,
        seconds=elapsed,
        status="ok",
    )


def _run_semchunk(texts: list[str]) -> RealResult:
    module = _optional_import("semchunk")
    if module is None:
        raise ImportError("semchunk is unavailable")

    tokenizer = _gpt4_tokenizer()
    chunkerify = getattr(module, "chunkerify", None)
    if not callable(chunkerify):
        raise RuntimeError("semchunk chunkerify is unavailable")

    def token_counter(s: str) -> int:
        return len(tokenizer.encode(s))

    chunker = chunkerify(token_counter, chunk_size=512)

    started = perf_counter()
    total_chunks = 0
    total_tokens = 0
    for text in texts:
        tokens = tokenizer.encode(text)
        total_tokens += len(tokens)
        total_chunks += len(list(chunker(text)))
    elapsed = perf_counter() - started

    total_chars = sum(len(text) for text in texts)
    avg_chunk = total_tokens / total_chunks if total_chunks > 0 else 0.0

    return RealResult(
        tool="semchunk",
        total_texts=len(texts),
        total_chars=total_chars,
        total_tokens=total_tokens,
        total_chunks=total_chunks,
        avg_chunk_tokens=avg_chunk,
        seconds=elapsed,
        status="ok",
    )


def _run_semantic_text_splitter(texts: list[str]) -> RealResult:
    module = _optional_import("semantic_text_splitter")
    if module is None:
        raise ImportError("semantic_text_splitter is unavailable")

    tokenizer = _gpt4_tokenizer()
    splitter = module.TextSplitter(512)  # char-based; we'll report char counts

    started = perf_counter()
    total_chunks = 0
    total_tokens = 0
    for text in texts:
        tokens = tokenizer.encode(text)
        total_tokens += len(tokens)
        chunks = splitter.chunks(text)
        total_chunks += len(chunks)
    elapsed = perf_counter() - started

    total_chars = sum(len(text) for text in texts)
    avg_chunk = total_tokens / total_chunks if total_chunks > 0 else 0.0

    return RealResult(
        tool="semantic_text_splitter",
        total_texts=len(texts),
        total_chars=total_chars,
        total_tokens=total_tokens,
        total_chunks=total_chunks,
        avg_chunk_tokens=avg_chunk,
        seconds=elapsed,
        status="ok",
    )


def _run_with_fallback(
    tool_name: str,
    runner: Callable[[list[str]], RealResult],
    texts: list[str],
) -> RealResult:
    try:
        return runner(texts)
    except ImportError as exc:
        return RealResult(
            tool=tool_name,
            total_texts=len(texts),
            total_chars=0,
            total_tokens=0,
            total_chunks=-1,
            avg_chunk_tokens=0.0,
            seconds=0.0,
            status="unavailable",
            detail=str(exc),
        )
    except Exception as exc:
        return RealResult(
            tool=tool_name,
            total_texts=len(texts),
            total_chars=0,
            total_tokens=0,
            total_chunks=-1,
            avg_chunk_tokens=0.0,
            seconds=0.0,
            status="error",
            detail=f"{type(exc).__name__}: {exc}",
        )


def run() -> int:
    print("Loading NLTK Gutenberg corpus...")
    fileids = gutenberg.fileids()
    texts = [gutenberg.raw(f) for f in fileids]

    runners: list[tuple[str, Callable[[list[str]], RealResult]]] = [
        ("omnichunk", _run_omnichunk),
        ("langchain_recursive", _run_langchain_recursive),
        ("semantic_text_splitter", _run_semantic_text_splitter),
        ("semchunk", _run_semchunk),
    ]

    print("Tool,Texts,Chars,Tokens,Chunks,AvgChunkTokens,Seconds,ThroughputMBps,Status,Detail")
    for tool_name, runner in runners:
        result = _run_with_fallback(tool_name, runner, texts)
        mbps = (result.total_chars / (1024 * 1024)) / result.seconds if result.seconds > 0 else 0.0
        print(
            f"{result.tool},{result.total_texts},{result.total_chars},{result.total_tokens},"
            f"{result.total_chunks},{result.avg_chunk_tokens:.3f},{result.seconds:.3f},{mbps:.3f},"
            f"{result.status},{result.detail.replace(',', ';')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())

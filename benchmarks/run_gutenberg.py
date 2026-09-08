# ruff: noqa: E402
"""Gutenberg timing with a shared cl100k_base budget and measured output sizes.

The corpus must already be installed; this runner does not download it. Timings
cover splitting, while input/output token auditing happens outside that timer.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from omnichunk import Chunker

TOKENIZER = "cl100k_base"
TOKEN_BUDGET = 512


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
    total_bytes: int = 0
    output_tokens: int = 0
    max_chunk_tokens: int = 0
    overflow_chunks: int = 0


def _optional_import(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _cl100k_tokenizer() -> Any:
    import tiktoken

    return tiktoken.get_encoding(TOKENIZER)


def _measure(
    tool: str,
    texts: list[str],
    split: Callable[[str], Iterable[str]],
    tokenizer: Any,
) -> RealResult:
    total_chunks = output_tokens = max_tokens = overflow_chunks = 0
    elapsed = 0.0
    total_tokens = sum(len(tokenizer.encode(text)) for text in texts)
    for text in texts:
        started = perf_counter()
        chunks = list(split(text))
        elapsed += perf_counter() - started
        for chunk in chunks:
            count = len(tokenizer.encode(chunk))
            total_chunks += 1
            output_tokens += count
            max_tokens = max(max_tokens, count)
            overflow_chunks += count > TOKEN_BUDGET
    return RealResult(
        tool=tool,
        total_texts=len(texts),
        total_chars=sum(map(len, texts)),
        total_bytes=sum(len(text.encode("utf-8")) for text in texts),
        total_tokens=total_tokens,
        total_chunks=total_chunks,
        output_tokens=output_tokens,
        avg_chunk_tokens=output_tokens / total_chunks if total_chunks else 0.0,
        max_chunk_tokens=max_tokens,
        overflow_chunks=overflow_chunks,
        seconds=elapsed,
        status="overflow" if overflow_chunks else "ok",
        detail=f"{TOKENIZER}; budget={TOKEN_BUDGET}; overlap=0; context=none",
    )


def _run_omnichunk(texts: list[str]) -> RealResult:
    chunker = Chunker()
    tokenizer = _cl100k_tokenizer()

    def split(text: str) -> Iterable[str]:
        return (
            chunk.contextualized_text
            for chunk in chunker.chunk(
                "gutenberg.txt",
                text,
                max_chunk_size=TOKEN_BUDGET,
                min_chunk_size=128,
                size_unit="tokens",
                tokenizer=TOKENIZER,
                overlap=0,
                context_mode="none",
            )
        )

    return _measure("omnichunk", texts, split, tokenizer)


def _run_langchain_recursive(texts: list[str]) -> RealResult:
    module = _optional_import("langchain_text_splitters")
    if module is None:
        module = _optional_import("langchain.text_splitter")
    splitter_cls = getattr(module, "RecursiveCharacterTextSplitter", None)
    if splitter_cls is None:
        raise ImportError("langchain RecursiveCharacterTextSplitter is unavailable")
    tokenizer = _cl100k_tokenizer()
    splitter = splitter_cls(
        length_function=lambda text: len(tokenizer.encode(text)),
        chunk_size=TOKEN_BUDGET,
        chunk_overlap=0,
        separators=["\n\n", "\n", " ", ""],
    )
    return _measure("langchain_recursive", texts, splitter.split_text, tokenizer)


def _run_semchunk(texts: list[str]) -> RealResult:
    module = _optional_import("semchunk")
    chunkerify = getattr(module, "chunkerify", None)
    if not callable(chunkerify):
        raise ImportError("semchunk chunkerify with an explicit counter is unavailable")
    tokenizer = _cl100k_tokenizer()
    chunker = chunkerify(lambda text: len(tokenizer.encode(text)), chunk_size=TOKEN_BUDGET)
    return _measure("semchunk", texts, lambda text: chunker(text, overlap=0), tokenizer)


def _run_semantic_text_splitter(texts: list[str]) -> RealResult:
    module = _optional_import("semantic_text_splitter")
    factory = getattr(getattr(module, "TextSplitter", None), "from_callback", None)
    if not callable(factory):
        raise ImportError("semantic_text_splitter lacks an explicit tokenizer callback API")
    tokenizer = _cl100k_tokenizer()
    splitter = factory(lambda text: len(tokenizer.encode(text)), TOKEN_BUDGET, overlap=0)
    return _measure("semantic_text_splitter", texts, splitter.chunks, tokenizer)


def _run_with_fallback(
    tool_name: str,
    runner: Callable[[list[str]], RealResult],
    texts: list[str],
) -> RealResult:
    try:
        return runner(texts)
    except Exception as exc:
        return RealResult(
            tool=tool_name,
            total_texts=len(texts),
            total_chars=sum(map(len, texts)),
            total_bytes=sum(len(text.encode("utf-8")) for text in texts),
            total_tokens=0,
            total_chunks=-1,
            avg_chunk_tokens=0.0,
            seconds=0.0,
            status="unavailable" if isinstance(exc, ImportError) else "error",
            detail=f"{type(exc).__name__}: {exc}",
        )


def run() -> int:
    from nltk.corpus import gutenberg

    print("Loading installed NLTK Gutenberg corpus...")
    texts = [gutenberg.raw(fileid) for fileid in gutenberg.fileids()]
    runners: list[tuple[str, Callable[[list[str]], RealResult]]] = [
        ("omnichunk", _run_omnichunk),
        ("langchain_recursive", _run_langchain_recursive),
        ("semantic_text_splitter", _run_semantic_text_splitter),
        ("semchunk", _run_semchunk),
    ]
    print(
        "Tool,Texts,Chars,UTF8Bytes,InputTokens,OutputTokens,Chunks,AvgChunkTokens,"
        "MaxChunkTokens,OverflowChunks,Seconds,ThroughputMiBps,Status,Detail"
    )
    results = [_run_with_fallback(tool, runner, texts) for tool, runner in runners]
    for result in results:
        mibps = (result.total_bytes / (1024 * 1024)) / result.seconds if result.seconds > 0 else 0.0
        print(
            f"{result.tool},{result.total_texts},{result.total_chars},{result.total_bytes},"
            f"{result.total_tokens},{result.output_tokens},{result.total_chunks},"
            f"{result.avg_chunk_tokens:.3f},{result.max_chunk_tokens},{result.overflow_chunks},"
            f"{result.seconds:.3f},{mibps:.3f},{result.status},{result.detail.replace(',', ';')}"
        )
    return int(any(result.status in {"error", "overflow"} for result in results))


if __name__ == "__main__":
    raise SystemExit(run())

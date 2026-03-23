from __future__ import annotations

import fnmatch
import time
import warnings
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Literal

from omnichunk.engine.router import route_content, route_content_stream
from omnichunk.formats.chunk import chunk_loaded_document
from omnichunk.formats.docx_loader import load_docx_bytes
from omnichunk.formats.ipynb import load_ipynb
from omnichunk.formats.pdf import load_pdf_bytes
from omnichunk.formats.tex import load_latex
from omnichunk.otel.util import finalize_chunk_file_span, maybe_span
from omnichunk.propositions.heuristic import extract_propositions_heuristic
from omnichunk.propositions.llm_extract import extract_propositions_llm
from omnichunk.propositions.types import Proposition
from omnichunk.quality import compute_chunk_quality_scores, compute_chunk_stats
from omnichunk.serialization import (
    chunk_to_dict,
    chunks_to_csv,
    chunks_to_jsonl,
    chunks_to_langchain_docs,
    chunks_to_llamaindex_docs,
    chunks_to_pinecone_vectors,
    chunks_to_supabase_rows,
    chunks_to_weaviate_objects,
)
from omnichunk.types import (
    BatchResult,
    Chunk,
    ChunkDiff,
    ChunkOptions,
    ChunkQualityScore,
    ChunkStats,
    ChunkTree,
    UpsertBatch,
)
from omnichunk.util.detect import detect_language

_STRUCTURED_SUFFIXES = frozenset({".ipynb", ".tex", ".pdf", ".docx"})


class Chunker:
    def __init__(self, **options: object) -> None:
        """Create reusable chunker with default options."""
        self._defaults = ChunkOptions(**_coerce_option_dict(options))

    def chunk(self, filepath: str, content: str, **overrides: object) -> list[Chunk]:
        """Chunk content and return all chunks."""
        path = Path(filepath)
        if path.suffix.lower() in _STRUCTURED_SUFFIXES:
            suf = path.suffix.lower()
            if suf in (".pdf", ".docx"):
                raise ValueError(
                    f"Use chunk_file() for {suf} documents; "
                    "binary formats cannot be passed as text."
                )
            loaded = load_ipynb(content) if suf == ".ipynb" else load_latex(content)
            options = self._build_options(filepath=filepath, overrides=overrides)
            lang = detect_language(filepath=filepath, content=loaded.text)
            options = replace(options, language=lang)
            return chunk_loaded_document(filepath, loaded, options)
        options = self._build_options(filepath=filepath, overrides=overrides)
        _, chunks = route_content(filepath=filepath, content=content, options=options)
        return chunks

    def stream(self, filepath: str, content: str, **overrides: object) -> Iterator[Chunk]:
        """Yield chunks one by one without buffering the full result.

        ``total_chunks`` is ``-1`` for every yielded chunk. Token overlap
        (``overlap=``) is not applied in streaming mode; use :meth:`chunk` for overlap.
        """
        path = Path(filepath)
        if path.suffix.lower() in _STRUCTURED_SUFFIXES:
            yield from self.chunk(filepath, content, **overrides)
            return
        options = self._build_options(filepath=filepath, overrides=overrides)
        _, stream = route_content_stream(filepath=filepath, content=content, options=options)
        yield from stream

    def batch(
        self,
        files: list[dict],
        concurrency: int = 10,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[BatchResult]:
        """Process multiple files concurrently. Each dict has 'filepath' and 'code' keys."""
        if not files:
            return []

        concurrency = max(1, min(concurrency, len(files)))
        results_by_idx: dict[int, BatchResult] = {}

        def _worker(idx: int, item: dict) -> tuple[int, BatchResult]:
            filepath = str(item.get("filepath", ""))
            code = str(item.get("code", ""))
            try:
                chunks = self.chunk(filepath=filepath, content=code)
                return idx, BatchResult(filepath=filepath, chunks=chunks)
            except Exception as exc:
                return idx, BatchResult(filepath=filepath, chunks=[], error=str(exc))

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(_worker, idx, file_item) for idx, file_item in enumerate(files)
            ]
            total = len(futures)
            for completed, future in enumerate(as_completed(futures), start=1):
                idx, result = future.result()
                results_by_idx[idx] = result
                if on_progress:
                    on_progress(completed, total, result.filepath)

        return [results_by_idx[idx] for idx in range(len(files))]

    def chunk_file(self, path: str, *, encoding: str = "utf-8", **overrides: object) -> list[Chunk]:
        """Read file from disk and chunk it."""
        file_path = Path(path)
        opts = self._build_options(filepath=str(file_path), overrides=overrides)
        tracer = opts.otel_tracer
        t0 = time.perf_counter()
        try:
            sz = int(file_path.stat().st_size)
        except OSError:
            sz = 0
        with maybe_span(
            tracer,
            "omnichunk.chunk_file",
            filepath=str(file_path.resolve()),
            omnichunk_file_size_bytes=sz,
        ) as span:
            try:
                if file_path.suffix.lower() in _STRUCTURED_SUFFIXES:
                    suf = file_path.suffix.lower()
                    if suf == ".ipynb":
                        loaded = load_ipynb(file_path.read_text(encoding=encoding))
                    elif suf == ".tex":
                        loaded = load_latex(file_path.read_text(encoding=encoding))
                    elif suf == ".pdf":
                        loaded = load_pdf_bytes(file_path.read_bytes())
                    else:
                        loaded = load_docx_bytes(file_path.read_bytes())
                    options = self._build_options(filepath=str(file_path), overrides=overrides)
                    lang = detect_language(filepath=str(file_path), content=loaded.text)
                    options = replace(options, language=lang)
                    out = chunk_loaded_document(str(file_path), loaded, options)
                else:
                    text = file_path.read_text(encoding=encoding)
                    out = self.chunk(filepath=str(file_path), content=text, **overrides)
            except BaseException as exc:
                finalize_chunk_file_span(span, chunk_count=0, t0=t0, error=str(exc))
                raise
            finalize_chunk_file_span(span, chunk_count=len(out), t0=t0)
            return out

    def chunk_directory(
        self,
        path: str,
        *,
        glob: str = "**/*",
        exclude: Sequence[str] | None = None,
        concurrency: int = 10,
        encoding: str = "utf-8",
        include_hidden: bool = False,
        **overrides: object,
    ) -> list[BatchResult]:
        """Chunk all matching files inside a directory recursively."""
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"Directory does not exist: {path}")

        if root.is_file():
            try:
                chunks = self.chunk_file(str(root), encoding=encoding, **overrides)
                return [BatchResult(filepath=str(root), chunks=chunks)]
            except Exception as exc:
                return [BatchResult(filepath=str(root), chunks=[], error=str(exc))]

        patterns = list(exclude or [])
        file_paths = _collect_directory_files(
            root,
            glob_pattern=glob,
            exclude_patterns=patterns,
            include_hidden=include_hidden,
        )
        if not file_paths:
            return []

        concurrency = max(1, min(concurrency, len(file_paths)))
        results_by_idx: dict[int, BatchResult] = {}

        def _worker(idx: int, file_path: Path) -> tuple[int, BatchResult]:
            filepath = str(file_path)
            if file_path.suffix.lower() in _STRUCTURED_SUFFIXES:
                try:
                    chunks = self.chunk_file(filepath, encoding=encoding, **overrides)
                    return idx, BatchResult(filepath=filepath, chunks=chunks)
                except Exception as exc:
                    return idx, BatchResult(filepath=filepath, chunks=[], error=str(exc))

            opts_w = self._build_options(filepath=filepath, overrides=overrides)
            tracer = opts_w.otel_tracer
            t0 = time.perf_counter()
            try:
                sz = int(file_path.stat().st_size)
            except OSError:
                sz = 0
            with maybe_span(
                tracer,
                "omnichunk.chunk_file",
                filepath=filepath,
                omnichunk_file_size_bytes=sz,
            ) as span:
                try:
                    text = file_path.read_text(encoding=encoding)
                except Exception as exc:
                    finalize_chunk_file_span(
                        span,
                        chunk_count=0,
                        t0=t0,
                        error=f"Read failed: {exc}",
                    )
                    err_read = f"Read failed: {exc}"
                    return idx, BatchResult(filepath=filepath, chunks=[], error=err_read)
                try:
                    chunks = self.chunk(filepath=filepath, content=text, **overrides)
                except Exception as exc:
                    finalize_chunk_file_span(span, chunk_count=0, t0=t0, error=str(exc))
                    return idx, BatchResult(filepath=filepath, chunks=[], error=str(exc))
                finalize_chunk_file_span(span, chunk_count=len(chunks), t0=t0)
                return idx, BatchResult(filepath=filepath, chunks=chunks)

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(_worker, idx, file_path)
                for idx, file_path in enumerate(file_paths)
            ]
            for future in as_completed(futures):
                idx, result = future.result()
                results_by_idx[idx] = result

        return [results_by_idx[idx] for idx in range(len(file_paths))]

    def to_dicts(self, chunks: Sequence[Chunk]) -> list[dict[str, Any]]:
        """Convert chunks into JSON-serializable dictionaries."""
        return [chunk_to_dict(chunk) for chunk in chunks]

    def to_jsonl(self, chunks: Sequence[Chunk], output_path: str | None = None) -> str:
        """Export chunks as JSONL text and optionally write to file."""
        return chunks_to_jsonl(chunks, output_path=output_path)

    def to_csv(self, chunks: Sequence[Chunk], output_path: str | None = None) -> str:
        """Export chunks as CSV text and optionally write to file."""
        return chunks_to_csv(chunks, output_path=output_path)

    def to_langchain_docs(
        self,
        chunks: Sequence[Chunk],
        *,
        use_contextualized_text: bool = True,
    ) -> list[Any]:
        """Convert chunks to LangChain Document objects."""
        return chunks_to_langchain_docs(
            chunks,
            use_contextualized_text=use_contextualized_text,
        )

    def to_llamaindex_docs(
        self,
        chunks: Sequence[Chunk],
        *,
        use_contextualized_text: bool = True,
    ) -> list[Any]:
        """Convert chunks to LlamaIndex Document objects."""
        return chunks_to_llamaindex_docs(
            chunks,
            use_contextualized_text=use_contextualized_text,
        )

    def to_pinecone_vectors(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[list[float]],
        *,
        namespace: str = "",
        use_contextualized_text: bool = True,
    ) -> list[dict[str, Any]]:
        """Build Pinecone upsert-ready dicts (caller supplies embeddings)."""
        return chunks_to_pinecone_vectors(
            chunks,
            embeddings,
            namespace=namespace,
            use_contextualized_text=use_contextualized_text,
        )

    def to_weaviate_objects(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[list[float]],
        *,
        class_name: str = "OmnichunkDocument",
        use_contextualized_text: bool = True,
    ) -> list[dict[str, Any]]:
        """Build Weaviate batch-import-ready dicts (caller supplies embeddings)."""
        return chunks_to_weaviate_objects(
            chunks,
            embeddings,
            class_name=class_name,
            use_contextualized_text=use_contextualized_text,
        )

    def to_supabase_rows(
        self,
        chunks: Sequence[Chunk],
        embeddings: Sequence[list[float]],
        *,
        use_contextualized_text: bool = True,
    ) -> list[dict[str, Any]]:
        """Build Supabase/pgvector-ready rows (caller supplies embeddings)."""
        return chunks_to_supabase_rows(
            chunks,
            embeddings,
            use_contextualized_text=use_contextualized_text,
        )

    def stream_upsert(
        self,
        path: str,
        *,
        embed_fn: Callable[[Sequence[str]], Sequence[Sequence[float]]],
        adapter: Literal["pinecone", "weaviate", "supabase"] = "pinecone",
        batch_size: int = 100,
        glob: str = "**/*",
        exclude: Sequence[str] | None = None,
        include_hidden: bool = False,
        encoding: str = "utf-8",
        namespace: str = "",
        class_name: str = "OmnichunkDocument",
        use_contextualized_text: bool = True,
        **overrides: object,
    ) -> Iterator[UpsertBatch]:
        """Yield embedding batches and adapter-ready rows without buffering all chunks.

        Memory use is O(batch_size) for chunk objects plus one batch of embeddings.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        def _flush(buf: list[Chunk]) -> UpsertBatch:
            texts = [
                c.contextualized_text if use_contextualized_text else c.text for c in buf
            ]
            emb_seq = embed_fn(texts)
            embeddings = [list(row) for row in emb_seq]
            if len(embeddings) != len(buf):
                raise ValueError(
                    f"embed_fn returned {len(embeddings)} vectors for {len(buf)} chunks"
                )
            if adapter == "pinecone":
                rows = chunks_to_pinecone_vectors(
                    buf,
                    embeddings,
                    namespace=namespace,
                    use_contextualized_text=use_contextualized_text,
                )
            elif adapter == "weaviate":
                rows = chunks_to_weaviate_objects(
                    buf,
                    embeddings,
                    class_name=class_name,
                    use_contextualized_text=use_contextualized_text,
                )
            else:
                rows = chunks_to_supabase_rows(
                    buf,
                    embeddings,
                    use_contextualized_text=use_contextualized_text,
                )
            return UpsertBatch(adapter=adapter, rows=rows, chunks=tuple(buf))

        buffer: list[Chunk] = []

        def _push(ch: Chunk) -> Iterator[UpsertBatch]:
            buffer.append(ch)
            while len(buffer) >= batch_size:
                batch = buffer[:batch_size]
                del buffer[:batch_size]
                yield _flush(batch)

        if root.is_file():
            for ch in self.chunk_file(str(root), encoding=encoding, **overrides):
                yield from _push(ch)
            if buffer:
                yield _flush(buffer)
            return

        file_paths = _collect_directory_files(
            root,
            glob_pattern=glob,
            exclude_patterns=list(exclude or []),
            include_hidden=include_hidden,
        )
        for fp in file_paths:
            try:
                for ch in self.chunk_file(str(fp), encoding=encoding, **overrides):
                    yield from _push(ch)
            except (OSError, UnicodeDecodeError):
                continue
        if buffer:
            yield _flush(buffer)

    def extract_propositions(
        self,
        filepath: str,
        text: str,
        *,
        mode: Literal["heuristic", "llm"] = "heuristic",
        llm_fn: Callable[[str, str], str] | None = None,
        **overrides: object,
    ) -> list[Proposition]:
        """Extract atomic factual claims with UTF-8 byte ranges into the source ``text``.

        - ``heuristic``: regex over sentences; no extra dependencies.
        - ``llm``: ``llm_fn(filepath, text)`` returns JSON with a ``claims`` list of objects
          containing ``text`` (verbatim quotes from ``text``; unmatched claims are skipped).
        """
        _ = self._build_options(filepath=filepath, overrides=overrides)
        if mode == "heuristic":
            return extract_propositions_heuristic(filepath, text)
        if llm_fn is None:
            raise ValueError(
                "extract_propositions(mode='llm') requires llm_fn(filepath, text) -> str"
            )
        props, warns = extract_propositions_llm(filepath, text, llm_fn=llm_fn)
        for w in warns:
            warnings.warn(w, UserWarning, stacklevel=2)
        return props

    def quality_scores(
        self,
        chunks: Sequence[Chunk],
        *,
        min_chunk_size: int | None = None,
        max_chunk_size: int | None = None,
        size_unit: str | None = None,
    ) -> list[ChunkQualityScore]:
        """Score chunk quality using entity, scope, and size heuristics."""
        resolved_min = (
            self._defaults.min_chunk_size if min_chunk_size is None else int(min_chunk_size)
        )
        resolved_max = (
            self._defaults.max_chunk_size if max_chunk_size is None else int(max_chunk_size)
        )
        resolved_unit = self._defaults.size_unit if size_unit is None else str(size_unit)
        return compute_chunk_quality_scores(
            chunks,
            min_chunk_size=resolved_min,
            max_chunk_size=resolved_max,
            size_unit=resolved_unit,
        )

    def chunk_stats(self, chunks: Sequence[Chunk], *, size_unit: str | None = None) -> ChunkStats:
        """Compute aggregate chunk statistics."""
        resolved_unit = self._defaults.size_unit if size_unit is None else str(size_unit)
        return compute_chunk_stats(chunks, size_unit=resolved_unit)

    def semantic_chunk(
        self,
        filepath: str,
        content: str,
        embed_fn: Callable[[list[str]], Any],
        *,
        window: int = 3,
        threshold: float = 0.3,
        **overrides: object,
    ) -> list[Chunk]:
        """Semantic chunking shortcut — sets semantic=True and semantic_embed_fn."""
        return self.chunk(
            filepath,
            content,
            semantic=True,
            semantic_embed_fn=embed_fn,
            semantic_window=window,
            semantic_threshold=threshold,
            **overrides,
        )

    def hierarchical_chunk(
        self,
        filepath: str,
        content: str,
        *,
        levels: Sequence[int],
        size_unit: str | None = None,
        **overrides: object,
    ) -> ChunkTree:
        """Build a multi-level ChunkTree (finest → coarsest by ascending ``levels``)."""
        from omnichunk.hierarchy.builder import build_chunk_tree

        resolved_unit = size_unit or self._defaults.size_unit
        merged = asdict(self._defaults)
        merged.update(_coerce_option_dict(overrides))
        skip = frozenset({"max_chunk_size", "min_chunk_size", "filepath", "tokenizer", "size_unit"})
        opts = {
            k: v
            for k, v in merged.items()
            if k in ChunkOptions.__dataclass_fields__
            and not str(k).startswith("_")
            and k not in skip
        }
        return build_chunk_tree(
            filepath,
            content,
            levels=list(levels),
            size_unit=str(resolved_unit),
            tokenizer=self._defaults.tokenizer,
            **opts,
        )

    def chunk_diff(
        self,
        filepath: str,
        new_content: str,
        *,
        previous_chunks: Sequence[Chunk],
        **overrides: object,
    ) -> ChunkDiff:
        """Incremental diff for vector DB updates (stable IDs match Pinecone export)."""
        from omnichunk.diff.engine import chunk_diff as _engine_chunk_diff

        merged = asdict(self._defaults)
        merged.update(_coerce_option_dict(overrides))
        clean = {
            k: v
            for k, v in merged.items()
            if k in ChunkOptions.__dataclass_fields__
            and not str(k).startswith("_")
        }
        child = Chunker(**clean)
        return _engine_chunk_diff(
            filepath,
            new_content,
            previous_chunks=previous_chunks,
            chunker=child,
        )

    async def achunk(
        self,
        filepath: str,
        content: str,
        **kwargs: object,
    ) -> list[Chunk]:
        """Async version of :meth:`chunk`. Runs chunking in the default thread pool executor."""
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.chunk(filepath, content, **kwargs),
        )

    async def astream(
        self,
        filepath: str,
        content: str,
        **kwargs: object,
    ) -> AsyncIterator[Chunk]:
        """Async streaming; yields chunks as they are produced (``total_chunks`` is ``-1``).

        Overlap is not applied; see :meth:`stream`.
        """
        import asyncio

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Chunk | BaseException | None] = asyncio.Queue()

        def _produce() -> None:
            try:
                for ch in self.stream(filepath, content, **kwargs):
                    loop.call_soon_threadsafe(queue.put_nowait, ch)
            except BaseException as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        producer_future = loop.run_in_executor(None, _produce)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            await producer_future

    async def abatch(
        self,
        inputs: list[dict],
        concurrency: int = 8,
    ) -> list[BatchResult]:
        """Process many files concurrently (each dict: ``filepath``, ``code``, optional options)."""
        import asyncio

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _process(item: dict) -> BatchResult:
            async with semaphore:
                filepath = str(item.get("filepath", ""))
                code = str(item.get("code", ""))
                extra = {k: v for k, v in item.items() if k not in ("filepath", "code")}
                try:
                    chunks = await self.achunk(filepath, code, **extra)
                    return BatchResult(filepath=filepath, chunks=chunks)
                except Exception as exc:
                    return BatchResult(filepath=filepath, error=str(exc))

        tasks = [asyncio.create_task(_process(item)) for item in inputs]
        return list(await asyncio.gather(*tasks))

    def _build_options(self, filepath: str, overrides: dict[str, object]) -> ChunkOptions:
        # Use replace(), not asdict(), so callables (otel_tracer, embed_fn) are not deep-copied.
        merged = _coerce_option_dict(overrides)
        return replace(self._defaults, filepath=filepath, **merged)


def chunk(filepath: str, content: str, **options: object) -> list[Chunk]:
    return Chunker(**options).chunk(filepath, content)


def chunk_file(path: str, encoding: str = "utf-8", **options: object) -> list[Chunk]:
    return Chunker(**options).chunk_file(path, encoding=encoding)


def chunk_directory(
    path: str,
    *,
    glob: str = "**/*",
    exclude: Sequence[str] | None = None,
    concurrency: int = 10,
    encoding: str = "utf-8",
    include_hidden: bool = False,
    **options: object,
) -> list[BatchResult]:
    return Chunker(**options).chunk_directory(
        path,
        glob=glob,
        exclude=exclude,
        concurrency=concurrency,
        encoding=encoding,
        include_hidden=include_hidden,
    )


def hierarchical_chunk(
    filepath: str,
    content: str,
    *,
    levels: Sequence[int],
    size_unit: str = "chars",
    **options: object,
) -> ChunkTree:
    return Chunker(**options).hierarchical_chunk(
        filepath, content, levels=levels, size_unit=size_unit
    )


def chunk_diff(
    filepath: str,
    new_content: str,
    *,
    previous_chunks: Sequence[Chunk],
    **options: object,
) -> ChunkDiff:
    return Chunker(**options).chunk_diff(
        filepath,
        new_content,
        previous_chunks=previous_chunks,
    )


def _collect_directory_files(
    root: Path,
    *,
    glob_pattern: str,
    exclude_patterns: Sequence[str],
    include_hidden: bool,
) -> list[Path]:
    candidates = [path for path in root.glob(glob_pattern) if path.is_file()]
    out: list[Path] = []

    for file_path in candidates:
        try:
            relative = file_path.relative_to(root)
        except Exception:
            relative = file_path

        relative_posix = relative.as_posix()
        if not include_hidden and any(part.startswith(".") for part in relative.parts):
            continue

        if exclude_patterns and any(
            fnmatch.fnmatch(relative_posix, pattern) for pattern in exclude_patterns
        ):
            continue

        out.append(file_path)

    out.sort(key=lambda item: item.as_posix())
    return out


def _coerce_option_dict(options: dict[str, object]) -> dict[str, Any]:
    allowed = set(ChunkOptions.__dataclass_fields__.keys())
    return {key: value for key, value in options.items() if key in allowed}

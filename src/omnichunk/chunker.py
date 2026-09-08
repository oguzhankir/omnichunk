from __future__ import annotations

import fnmatch
import hashlib
import json
import time
import warnings
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Literal

from omnichunk.config import (
    coerce_options,
    configuration_fingerprint,
    public_options,
    validate_options,
)
from omnichunk.engine.router import route_content_stream
from omnichunk.finalize import finalize_chunks, skipped_ranges, source_descriptor
from omnichunk.formats.chunk import _iter_loaded_chunks
from omnichunk.formats.docx_loader import load_docx_bytes
from omnichunk.formats.ipynb import load_ipynb
from omnichunk.formats.pdf import load_pdf_bytes
from omnichunk.formats.rst import load_rst
from omnichunk.formats.tex import load_latex
from omnichunk.formats.types import LoadedDocument
from omnichunk.otel.util import finalize_chunk_file_span, maybe_span, record_span_error, span_set
from omnichunk.plugins import PluginRegistry
from omnichunk.propositions.heuristic import extract_propositions_heuristic
from omnichunk.propositions.llm_extract import extract_propositions_llm
from omnichunk.propositions.types import Proposition
from omnichunk.quality import compute_chunk_quality_scores, compute_chunk_stats
from omnichunk.util.text_index import TextIndex

if TYPE_CHECKING:
    from omnichunk.semantic.cache import EmbeddingCache
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
    ChunkResult,
    ChunkStats,
    ChunkTree,
    UpsertBatch,
)
from omnichunk.util.detect import detect_language

_STRUCTURED_SUFFIXES = frozenset({".ipynb", ".tex", ".pdf", ".docx", ".rst"})


class Chunker:
    def __init__(self, *, registry: object = None, **options: object) -> None:
        """Create reusable chunker with default options."""
        if registry is not None and not isinstance(registry, PluginRegistry):
            raise TypeError("registry must be a PluginRegistry")
        self.registry = registry if registry is not None else PluginRegistry.from_global()
        coerced = _coerce_option_dict(options)
        if "max_chunk_size" in coerced and "min_chunk_size" not in coerced:
            coerced["min_chunk_size"] = min(50, int(coerced["max_chunk_size"]))
        self._defaults = ChunkOptions(**coerced)
        validate_options(self._defaults)
        self._embedding_cache: EmbeddingCache | None = None
        self._embedding_cache_lock = RLock()

    def semantic_cache_stats(self) -> dict[str, int]:
        """Return embedding cache ``{"hits", "misses", "size"}`` for this Chunker.

        The cache is per-instance and starts empty; a freshly constructed
        :class:`Chunker` always reports all-zero stats until semantic chunking
        runs at least once.
        """
        if self._embedding_cache is None:
            return {"hits": 0, "misses": 0, "size": 0}
        return self._embedding_cache.stats()

    def config_fingerprint(self) -> str:
        """Fingerprint of options and installed parser/tokenizer versions."""
        return self._configuration_fingerprint(self._defaults)

    def _configuration_fingerprint(self, options: ChunkOptions) -> str:
        payload = {
            "options": configuration_fingerprint(options),
            "plugins": self.registry.fingerprint,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def chunk(self, filepath: str, content: str, **overrides: object) -> list[Chunk]:
        """Chunk canonical content through the same finalization as stream()."""
        chunks = list(self.stream(filepath, content, **overrides))
        return [replace(c, total_chunks=len(chunks)) for c in chunks]

    def _finalize_loaded(
        self, filepath: str, loaded: LoadedDocument, options: ChunkOptions, encoding: str = "utf-8"
    ) -> Iterator[Chunk]:
        index = TextIndex(loaded.text)
        source = source_descriptor(
            filepath,
            index,
            options,
            format_name=loaded.format_name,
            encoding=encoding,
            metadata={"warnings": list(loaded.warnings)},
        )
        engine_options = replace(options, overlap=None, overlap_lines=0)
        proposed = self.registry.iterate(_loaded_candidates(filepath, loaded, engine_options))
        yield from finalize_chunks(
            filepath,
            loaded.text,
            proposed,
            options,
            index=index,
            source=source,
            fingerprint=self._configuration_fingerprint(options),
        )

    def stream(self, filepath: str, content: str, **overrides: object) -> Iterator[Chunk]:
        """Yield measured chunks with total_chunks=-1; source/AST stay resident.

        All engines share overlap and payload policies. Structured loaders and
        semantic boundary discovery may buffer their per-document candidates.
        """
        options = self._build_options(filepath=filepath, overrides=overrides)
        suffix = Path(filepath).suffix.lower()
        if suffix in (".pdf", ".docx"):
            raise ValueError(
                f"Use chunk_file() for {suffix} documents; binary formats cannot be passed as text."
            )
        if suffix in _STRUCTURED_SUFFIXES:
            if suffix == ".ipynb":
                loaded = load_ipynb(content, include_outputs=options.include_notebook_outputs)
            elif suffix == ".rst":
                loaded = load_rst(content)
            else:
                loaded = load_latex(content)
            yield from self._finalize_loaded(filepath, loaded, options)
            return
        index = TextIndex(content)
        engine_options = replace(
            options, overlap=None, overlap_lines=0, _precomputed_text_index=index
        )
        with maybe_span(
            options.otel_tracer, "omnichunk.engine.route", filepath=filepath
        ) as route_span:
            content_type, proposed = route_content_stream(filepath, content, engine_options)
            span_set(route_span, "omnichunk.engine_name", content_type.value)
            span_set(route_span, "omnichunk.size_unit", options.size_unit)
            yield from finalize_chunks(
                filepath,
                content,
                self.registry.iterate(proposed),
                options,
                index=index,
                fingerprint=self._configuration_fingerprint(options),
            )

    def chunk_with_manifest(self, filepath: str, content: str, **overrides: object) -> ChunkResult:
        """Return chunks plus source-span omissions, even for whitespace-only input.

        This text API takes canonical text. Use format loaders explicitly when
        inspecting a binary/document container's canonical extraction.
        """
        if Path(filepath).suffix.lower() in _STRUCTURED_SUFFIXES:
            raise ValueError(
                "chunk_with_manifest accepts canonical text; use a text filepath after loading"
            )
        options = self._build_options(filepath, overrides)
        chunks = self.chunk(filepath, content, **overrides)
        index = TextIndex(content)
        source = source_descriptor(filepath, index, options)
        diagnostics = tuple(dict.fromkeys(e for c in chunks for e in c.context.parse_errors))
        return ChunkResult(
            source, tuple(chunks), skipped_ranges(chunks, len(index.raw_bytes)), diagnostics
        )

    def stream_file(
        self, path: str, *, encoding: str = "utf-8", **overrides: object
    ) -> Iterator[Chunk]:
        """Iterate one file without collecting ordinary-text chunk objects."""
        file_path = Path(path)
        if file_path.suffix.lower() in (".pdf", ".docx"):
            for c in self.chunk_file(path, encoding=encoding, **overrides):
                yield replace(c, total_chunks=-1)
        else:
            for c in self.stream(str(file_path), _read_text(file_path, encoding), **overrides):
                yield _with_encoding(c, encoding)

    def batch(
        self,
        files: list[dict[str, Any]],
        concurrency: int = 10,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[BatchResult]:
        """Process multiple files concurrently. Each dict has 'filepath' and 'code' keys."""
        if not files:
            return []

        concurrency = max(1, min(concurrency, len(files)))
        results_by_idx: dict[int, BatchResult] = {}

        def _worker(idx: int, item: dict[str, Any]) -> tuple[int, BatchResult]:
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
                    options = self._build_options(filepath=str(file_path), overrides=overrides)
                    if suf == ".ipynb":
                        loaded = load_ipynb(
                            _read_text(file_path, encoding),
                            include_outputs=opts.include_notebook_outputs,
                        )
                    elif suf == ".tex":
                        loaded = load_latex(_read_text(file_path, encoding))
                    elif suf == ".rst":
                        loaded = load_rst(_read_text(file_path, encoding))
                    elif suf == ".pdf":
                        loaded = load_pdf_bytes(file_path.read_bytes())
                    else:
                        loaded = load_docx_bytes(file_path.read_bytes())
                    lang = detect_language(filepath=str(file_path), content=loaded.text)
                    options = replace(options, language=lang)
                    out = list(self._finalize_loaded(str(file_path), loaded, options, encoding))
                    out = [replace(c, total_chunks=len(out)) for c in out]
                else:
                    text = _read_text(file_path, encoding)
                    out = self.chunk(filepath=str(file_path), content=text, **overrides)
                    out = [_with_encoding(c, encoding) for c in out]
            except BaseException as exc:
                record_span_error(span, exc)
                finalize_chunk_file_span(span, chunk_count=0, t0=t0, error=str(exc))
                raise
            span_set(span, "omnichunk.size_unit", opts.size_unit)
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
                    text = _read_text(file_path, encoding)
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
                executor.submit(_worker, idx, file_path) for idx, file_path in enumerate(file_paths)
            ]
            for future in as_completed(futures):
                idx, result = future.result()
                results_by_idx[idx] = result

        return [results_by_idx[idx] for idx in range(len(file_paths))]

    def format(self, chunks: Sequence[Chunk], name: str) -> str:
        """Export using a formatter registered on this instance's registry."""
        formatter = self.registry.formatters.get(name)
        if formatter is None:
            raise ValueError(f"Unknown formatter: {name}")
        return formatter(chunks)

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

        Output buffering is O(batch_size). Source text/AST and structured or
        semantic candidates may remain resident for the current document.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if adapter not in ("pinecone", "weaviate", "supabase"):
            raise ValueError("Unknown vector adapter")

        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        def _flush(buf: list[Chunk]) -> UpsertBatch:
            texts = [c.contextualized_text if use_contextualized_text else c.text for c in buf]
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
            for ch in self.stream_file(str(root), encoding=encoding, **overrides):
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
                for ch in self.stream_file(str(fp), encoding=encoding, **overrides):
                    yield from _push(ch)
            except (OSError, UnicodeDecodeError):
                raise
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

        if Path(filepath).suffix.lower() in _STRUCTURED_SUFFIXES:
            raise ValueError(
                "hierarchical_chunk accepts canonical text; load structured documents first"
            )
        resolved_unit = size_unit or self._defaults.size_unit
        merged = public_options(self._defaults)
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
            tokenizer=merged["tokenizer"],
            registry=self.registry,
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

        merged = public_options(self._defaults)
        merged.update(_coerce_option_dict(overrides))
        clean = {
            k: v
            for k, v in merged.items()
            if k in ChunkOptions.__dataclass_fields__ and not str(k).startswith("_")
        }
        child = Chunker(registry=self.registry, **clean)
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
        self, filepath: str, content: str, *, buffer_size: int = 8, **kwargs: object
    ) -> AsyncIterator[Chunk]:
        """Bounded async output with backpressure and cooperative cancellation."""
        import asyncio
        from concurrent.futures import TimeoutError as FutureTimeout
        from threading import Event

        if buffer_size < 1:
            raise ValueError("buffer_size must be positive")
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Chunk | BaseException | None] = asyncio.Queue(maxsize=buffer_size)
        stopped = Event()

        def put(item: Chunk | BaseException | None) -> bool:
            future = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
            while not stopped.is_set():
                try:
                    future.result(timeout=0.05)
                    return True
                except FutureTimeout:
                    continue
            future.cancel()
            return False

        def produce() -> None:
            iterator = self.stream(filepath, content, **kwargs)
            try:
                for item in iterator:
                    if stopped.is_set() or not put(item):
                        break
            except BaseException as exc:
                if not stopped.is_set():
                    put(exc)
            finally:
                close = getattr(iterator, "close", None)
                if close is not None:
                    close()
                if not stopped.is_set():
                    put(None)

        producer = loop.run_in_executor(None, produce)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            stopped.set()
            await asyncio.shield(producer)

    async def abatch(
        self,
        inputs: list[dict[str, Any]],
        concurrency: int = 8,
    ) -> list[BatchResult]:
        """Process many files concurrently (each dict: ``filepath``, ``code``, optional options)."""
        import asyncio

        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _process(item: dict[str, Any]) -> BatchResult:
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
        merged["filepath"] = filepath
        if "max_chunk_size" in merged and "min_chunk_size" not in merged:
            merged["min_chunk_size"] = min(
                self._defaults.min_chunk_size, int(merged["max_chunk_size"])
            )
        options = replace(self._defaults, **merged)
        validate_options(options)
        return self._with_cached_embed_fn(options)

    def _with_cached_embed_fn(self, options: ChunkOptions) -> ChunkOptions:
        """Wrap ``semantic_embed_fn`` with this Chunker's per-instance LRU cache.

        No-op unless semantic chunking is requested with a callable embed_fn
        and a positive cache size. The wrapper is idempotent because it stores
        the wrapped function back on the options it returns.
        """
        if not options.semantic:
            return options
        embed_fn = options.semantic_embed_fn
        if not callable(embed_fn) or int(options.semantic_embed_cache_size) <= 0:
            return options
        with self._embedding_cache_lock:
            if (
                self._embedding_cache is None
                or self._embedding_cache._max != options.semantic_embed_cache_size
            ):
                from omnichunk.semantic.cache import EmbeddingCache

                self._embedding_cache = EmbeddingCache(options.semantic_embed_cache_size)
            cached = self._embedding_cache.wrap(
                embed_fn,
                namespace=options.semantic_cache_namespace,
                model_revision=options.semantic_model_revision,
                preprocessing=options.semantic_preprocessing,
            )
        return replace(options, semantic_embed_fn=cached)


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
    return coerce_options(options)


def _loaded_candidates(
    filepath: str, loaded: LoadedDocument, options: ChunkOptions
) -> Iterator[Chunk]:
    yield from _iter_loaded_chunks(filepath, loaded, options)


def _read_text(path: Path, encoding: str) -> str:
    with path.open(encoding=encoding, newline="") as handle:
        return handle.read()


def _with_encoding(chunk: Chunk, encoding: str) -> Chunk:
    if chunk.source is None:
        return chunk
    return replace(
        chunk,
        source=replace(
            chunk.source,
            encoding=encoding,
            normalization="none"
            if encoding.lower().replace("_", "-") == "utf-8"
            else f"decoded:{encoding}",
        ),
    )

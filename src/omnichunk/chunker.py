from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from omnichunk.engine.router import route_content, route_content_stream
from omnichunk.types import BatchResult, Chunk, ChunkOptions


class Chunker:
    def __init__(self, **options: object) -> None:
        """Create reusable chunker with default options."""
        self._defaults = ChunkOptions(**_coerce_option_dict(options))

    def chunk(self, filepath: str, content: str, **overrides: object) -> list[Chunk]:
        """Chunk content and return all chunks."""
        options = self._build_options(filepath=filepath, overrides=overrides)
        _, chunks = route_content(filepath=filepath, content=content, options=options)
        return chunks

    def stream(self, filepath: str, content: str, **overrides: object) -> Iterator[Chunk]:
        """Stream chunks one at a time (total_chunks = -1)."""
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

    def chunk_file(self, path: str, **overrides: object) -> list[Chunk]:
        """Read file from disk and chunk it."""
        text = Path(path).read_text(encoding="utf-8")
        return self.chunk(filepath=path, content=text, **overrides)

    def _build_options(self, filepath: str, overrides: dict[str, object]) -> ChunkOptions:
        data = asdict(self._defaults)
        data.update(_coerce_option_dict(overrides))
        data["filepath"] = filepath
        return ChunkOptions(**data)


def chunk(filepath: str, content: str, **options: object) -> list[Chunk]:
    return Chunker(**options).chunk(filepath, content)


def chunk_file(path: str, **options: object) -> list[Chunk]:
    return Chunker(**options).chunk_file(path)


def _coerce_option_dict(options: dict[str, object]) -> dict[str, Any]:
    allowed = set(ChunkOptions.__dataclass_fields__.keys())
    return {key: value for key, value in options.items() if key in allowed}

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable, Iterator

from omnichunk.engine.router import route_content
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
        chunks = self.chunk(filepath=filepath, content=content, **overrides)
        for idx, chunk in enumerate(chunks):
            yield Chunk(
                text=chunk.text,
                contextualized_text=chunk.contextualized_text,
                byte_range=chunk.byte_range,
                line_range=chunk.line_range,
                index=idx,
                total_chunks=-1,
                context=chunk.context,
                token_count=chunk.token_count,
                char_count=chunk.char_count,
                nws_count=chunk.nws_count,
            )

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
            futures = [executor.submit(_worker, idx, file_item) for idx, file_item in enumerate(files)]
            completed = 0
            total = len(futures)
            for future in as_completed(futures):
                idx, result = future.result()
                results_by_idx[idx] = result
                completed += 1
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


def _coerce_option_dict(options: dict[str, object]) -> dict[str, object]:
    allowed = set(ChunkOptions.__dataclass_fields__.keys())
    return {key: value for key, value in options.items() if key in allowed}

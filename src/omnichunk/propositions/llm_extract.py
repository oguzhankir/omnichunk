"""Optional LLM-backed proposition extraction (user-supplied ``llm_fn``).

Single-document extraction uses ``extract_propositions_llm``. For many chunks,
``extract_propositions_llm_batch`` packs several chunks into one LLM call
(cutting API cost), with retry/backoff and a per-call timeout;
``extract_propositions_stream`` yields propositions batch-by-batch.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from omnichunk.propositions.types import Proposition
from omnichunk.types import ByteRange
from omnichunk.util.text_index import TextIndex

# Batched call contract: llm_fn(filepath, payload) where payload is JSON
# {"chunks": [{"index": i, "text": ...}, ...]} and the response is JSON
# {"results": [{"claims": [{"text": ..., "confidence": ...}, ...]}, ...]}
# aligned by chunk index.

_DEFAULT_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)


def _find_span_bytes(ti: TextIndex, full: str, quote: str) -> tuple[int, int] | None:
    if not quote.strip():
        return None
    idx = full.find(quote)
    if idx < 0:
        return None
    c0, c1 = idx, idx + len(quote)
    return ti.byte_offset_for_char(c0), ti.byte_offset_for_char(c1)


def extract_propositions_llm(
    filepath: str,
    text: str,
    *,
    llm_fn: Callable[[str, str], str],
) -> tuple[list[Proposition], list[str]]:
    """
    Ask ``llm_fn(filepath, text)`` for JSON: ``{\"claims\": [{\"text\": \"...\"}, ...]}``.
    Each claim must appear verbatim in ``text``; otherwise it is skipped and a warning is recorded.
    """
    raw = llm_fn(filepath, text)
    warnings: list[str] = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], [f"llm_fn returned invalid JSON: {e}"]

    claims = data.get("claims")
    if not isinstance(claims, list):
        return [], ["llm_fn JSON must contain a list 'claims'"]

    ti = TextIndex(text)
    out, warns = _claims_to_propositions(claims, text, ti, filepath=filepath, chunk_index=None)
    out.sort(key=lambda p: (p.byte_range.start, p.byte_range.end))
    return out, warnings + warns


def _chunk_text(chunk: Any) -> str:
    """Accept either a Chunk (``.text``) or a plain string."""
    return chunk if isinstance(chunk, str) else str(getattr(chunk, "text", ""))


def _claims_to_propositions(
    claims: list[Any],
    text: str,
    ti: TextIndex,
    *,
    filepath: str,
    chunk_index: int | None,
) -> tuple[list[Proposition], list[str]]:
    out: list[Proposition] = []
    warns: list[str] = []
    for i, item in enumerate(claims):
        if not isinstance(item, dict):
            warns.append(f"claim[{i}] is not an object")
            continue
        qt = item.get("text")
        if not isinstance(qt, str) or not qt.strip():
            warns.append(f"claim[{i}] missing string 'text'")
            continue
        span = _find_span_bytes(ti, text, qt)
        if span is None:
            warns.append(f"claim[{i}] text not found verbatim in source")
            continue
        bs, be = span
        meta: dict[str, Any] = {"source": "llm", "filepath": filepath, "index": i}
        if chunk_index is not None:
            meta["chunk_index"] = chunk_index
        out.append(
            Proposition(
                text=qt.strip(),
                byte_range=ByteRange(start=bs, end=be),
                confidence=float(item.get("confidence", 0.7)),
                metadata=meta,
            )
        )
    return out, warns


def _call_with_retry(
    llm_fn: Callable[[str, str], str],
    filepath: str,
    payload: str,
    *,
    timeout: float,
    max_retries: int,
    retry_delays: Sequence[float],
    sleep_fn: Callable[[float], None],
) -> tuple[str | None, list[str]]:
    """Call ``llm_fn`` with a timeout and exponential-backoff retries.

    Returns ``(response, warnings)``; ``response`` is ``None`` if every attempt
    failed. The timeout uses a worker thread; a timed-out call cannot be force
    killed (Python limitation) but its result is abandoned.
    """
    warns: list[str] = []
    attempts = max(1, max_retries)
    for attempt in range(attempts):
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(llm_fn, filepath, payload)
                return future.result(timeout=timeout), warns
        except FutureTimeoutError:
            warns.append(f"attempt {attempt + 1} timed out after {timeout}s")
        except Exception as exc:  # noqa: BLE001 - surface as warning, then retry
            warns.append(f"attempt {attempt + 1} failed: {exc}")
        if attempt < attempts - 1:
            delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
            sleep_fn(delay)
    return None, warns


def _iter_batches(chunks: Sequence[Any], batch_size: int) -> Iterator[tuple[int, list[Any]]]:
    size = max(1, int(batch_size))
    for base in range(0, len(chunks), size):
        yield base, list(chunks[base : base + size])


def _process_batch(
    base: int,
    batch: list[Any],
    *,
    llm_fn: Callable[[str, str], str],
    filepath: str,
    timeout: float,
    max_retries: int,
    retry_delays: Sequence[float],
    sleep_fn: Callable[[float], None],
) -> tuple[list[Proposition], list[str]]:
    texts = [_chunk_text(c) for c in batch]
    payload = json.dumps(
        {"filepath": filepath, "chunks": [{"index": i, "text": t} for i, t in enumerate(texts)]}
    )
    raw, warns = _call_with_retry(
        llm_fn,
        filepath,
        payload,
        timeout=timeout,
        max_retries=max_retries,
        retry_delays=retry_delays,
        sleep_fn=sleep_fn,
    )
    if raw is None:
        warns.append(f"batch at offset {base} produced no result after retries")
        return [], warns

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], warns + [f"batch at offset {base}: invalid JSON: {e}"]

    results = data.get("results")
    if not isinstance(results, list):
        return [], warns + [f"batch at offset {base}: response missing 'results' list"]

    out: list[Proposition] = []
    for local_idx, text in enumerate(texts):
        if local_idx >= len(results):
            warns.append(f"batch at offset {base}: missing result for chunk {local_idx}")
            continue
        entry = results[local_idx]
        claims = entry.get("claims") if isinstance(entry, dict) else None
        if not isinstance(claims, list):
            warns.append(f"batch at offset {base}: chunk {local_idx} missing 'claims'")
            continue
        ti = TextIndex(text)
        props, claim_warns = _claims_to_propositions(
            claims, text, ti, filepath=filepath, chunk_index=base + local_idx
        )
        props.sort(key=lambda p: (p.byte_range.start, p.byte_range.end))
        out.extend(props)
        warns.extend(claim_warns)
    return out, warns


def extract_propositions_llm_batch(
    chunks: Sequence[Any],
    *,
    llm_fn: Callable[[str, str], str],
    filepath: str = "",
    batch_size: int = 1,
    timeout: float = 30.0,
    max_retries: int = 3,
    retry_delays: Sequence[float] = _DEFAULT_RETRY_DELAYS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[list[Proposition], list[str]]:
    """Extract propositions from many chunks, packing ``batch_size`` per LLM call.

    Returns ``(propositions, warnings)``. Propositions preserve input chunk
    order (chunk 0's claims first, then chunk 1's, ...); each carries a
    ``chunk_index`` in its metadata. Byte ranges are relative to each chunk's
    own text.
    """
    all_props: list[Proposition] = []
    all_warns: list[str] = []
    for base, batch in _iter_batches(chunks, batch_size):
        props, warns = _process_batch(
            base,
            batch,
            llm_fn=llm_fn,
            filepath=filepath,
            timeout=timeout,
            max_retries=max_retries,
            retry_delays=retry_delays,
            sleep_fn=sleep_fn,
        )
        all_props.extend(props)
        all_warns.extend(warns)
    return all_props, all_warns


def extract_propositions_stream(
    chunks: Sequence[Any],
    *,
    llm_fn: Callable[[str, str], str],
    filepath: str = "",
    batch_size: int = 1,
    timeout: float = 30.0,
    max_retries: int = 3,
    retry_delays: Sequence[float] = _DEFAULT_RETRY_DELAYS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Iterator[Proposition]:
    """Yield propositions batch-by-batch, preserving input chunk order.

    Useful for long documents where you want to begin consuming propositions
    before every batch has been processed. Warnings are not surfaced here; use
    :func:`extract_propositions_llm_batch` when you need them.
    """
    for base, batch in _iter_batches(chunks, batch_size):
        props, _warns = _process_batch(
            base,
            batch,
            llm_fn=llm_fn,
            filepath=filepath,
            timeout=timeout,
            max_retries=max_retries,
            retry_delays=retry_delays,
            sleep_fn=sleep_fn,
        )
        yield from props

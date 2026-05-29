from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Literal, cast, overload

import numpy as np
from numpy.typing import NDArray


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer. Returns lowercase tokens."""
    return re.findall(r"[a-zA-Z][a-zA-Z0-9]*", text.lower())


def build_tfidf_matrix(
    documents: Sequence[str],
    *,
    max_vocab: int = 4096,
    min_df: int = 1,
) -> NDArray[Any]:
    """Build TF-IDF matrix of shape (N, V) for N documents, V vocab terms."""
    n_docs = len(documents)
    if n_docs == 0:
        return np.zeros((0, 1), dtype=np.float64)

    doc_tokens: list[list[str]] = [_tokenize(d) for d in documents]
    df: dict[str, int] = {}
    for tokens in doc_tokens:
        seen: set[str] = set()
        for t in tokens:
            if t not in seen:
                seen.add(t)
                df[t] = df.get(t, 0) + 1

    candidates = sorted(
        ((t, c) for t, c in df.items() if c >= min_df),
        key=lambda x: (-x[1], x[0]),
    )
    vocab = [t for t, _ in candidates[:max_vocab]]
    if not vocab:
        return np.zeros((n_docs, 1), dtype=np.float64)

    t2i = {t: i for i, t in enumerate(vocab)}
    v = len(vocab)
    tf_mat = np.zeros((n_docs, v), dtype=np.float64)
    for i, tokens in enumerate(doc_tokens):
        for tok in tokens:
            j = t2i.get(tok)
            if j is not None:
                tf_mat[i, j] += 1.0

    idf = np.zeros(v, dtype=np.float64)
    nd = float(n_docs)
    for j, term in enumerate(vocab):
        dfi = float(df[term])
        idf[j] = np.log((1.0 + nd) / (1.0 + dfi)) + 1.0

    out = np.zeros((n_docs, v), dtype=np.float64)
    for i in range(n_docs):
        for j in range(v):
            tf = tf_mat[i, j]
            if tf > 0:
                out[i, j] = (1.0 + np.log(tf)) * idf[j]

    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return cast("NDArray[Any]", out / norms)


def _coherence_scores(
    sentences: Sequence[str],
    *,
    window_size: int,
    max_vocab: int,
) -> NDArray[Any]:
    """Per-gap TF-IDF cosine similarity using sliding window means.

    Builds the sentence TF-IDF matrix once (no re-embedding), then for every
    gap ``g`` between ``sentences[g]`` and ``sentences[g+1]`` compares the mean
    vector of up to ``window_size`` sentences on each side. Window means are
    derived from a prefix-sum so the whole pass is O(N * V), independent of the
    window width. Returns an array of length ``N - 1``.
    """
    n = len(sentences)
    if n < 2:
        return np.zeros(0, dtype=np.float64)
    w = max(1, int(window_size))

    mat = build_tfidf_matrix(sentences, max_vocab=max_vocab)
    v = mat.shape[1]
    if v == 0:
        return np.zeros(n - 1, dtype=np.float64)

    # cum[i] == sum of mat[:i]; shape (n + 1, V).
    cum = np.zeros((n + 1, v), dtype=np.float64)
    cum[1:] = np.cumsum(mat, axis=0)

    gaps = np.arange(n - 1)
    lo_b = np.maximum(0, gaps - w + 1)
    cnt_b = (gaps + 1) - lo_b
    before = (cum[gaps + 1] - cum[lo_b]) / cnt_b[:, None]

    hi_a = np.minimum(n, gaps + 2 + (w - 1))
    cnt_a = hi_a - (gaps + 1)
    after = (cum[hi_a] - cum[gaps + 1]) / cnt_a[:, None]

    nb = np.linalg.norm(before, axis=1)
    na = np.linalg.norm(after, axis=1)
    denom = nb * na
    dots = np.einsum("id,id->i", before, after)
    sims = np.where(denom > 0, dots / np.where(denom == 0, 1.0, denom), 0.0)
    result: NDArray[Any] = sims.astype(np.float64)
    return result


@overload
def detect_topic_shifts(
    sentences: Sequence[str],
    *,
    window: int = ...,
    window_size: int | None = ...,
    threshold: float = ...,
    method: str = ...,
    k: float = ...,
    min_shift_gap: int = ...,
    max_vocab: int = ...,
    return_scores: Literal[False] = ...,
) -> tuple[int, ...]: ...


@overload
def detect_topic_shifts(
    sentences: Sequence[str],
    *,
    window: int = ...,
    window_size: int | None = ...,
    threshold: float = ...,
    method: str = ...,
    k: float = ...,
    min_shift_gap: int = ...,
    max_vocab: int = ...,
    return_scores: Literal[True],
) -> tuple[tuple[int, ...], list[float]]: ...


def detect_topic_shifts(
    sentences: Sequence[str],
    *,
    window: int = 5,
    window_size: int | None = None,
    threshold: float = 0.5,
    method: str = "fixed",
    k: float = 1.0,
    min_shift_gap: int = 3,
    max_vocab: int = 2048,
    return_scores: bool = False,
) -> tuple[int, ...] | tuple[tuple[int, ...], list[float]]:
    """Detect topic shifts from TF-IDF coherence over sliding windows.

    Each gap between adjacent sentences is scored by the cosine similarity of
    the mean TF-IDF vectors of the ``window_size`` sentences on each side
    (smoothing out single-sentence noise). A gap becomes a boundary when its
    score falls below the threshold.

    ``method="fixed"`` (default): use ``threshold`` directly.
    ``method="adaptive"``: ``threshold = mean(scores) - k * std(scores)``,
    making detection relative to the document's own similarity distribution —
    far more robust on homogeneous (all-code / all-prose) documents.

    ``window`` is retained for backward compatibility and is used as the
    window width when ``window_size`` is not given.

    With ``return_scores=True`` returns ``(shift_indices, scores)`` where
    ``scores[g]`` is the coherence score at the gap after ``sentences[g]``
    (``len(scores) == max(0, len(sentences) - 1)``), for plotting/debugging.
    """
    w = window if window_size is None else window_size
    scores = _coherence_scores(sentences, window_size=max(1, int(w)), max_vocab=max_vocab)

    if scores.size == 0:
        return ((), []) if return_scores else ()

    if method == "adaptive":
        thr = float(np.mean(scores) - float(k) * np.std(scores))
    elif method == "fixed":
        thr = float(threshold)
    else:
        raise ValueError(f"method must be 'fixed' or 'adaptive', got {method!r}")

    last_shift_after: int | None = None
    out: list[int] = []
    for g in range(scores.size):
        if float(scores[g]) < thr and (
            last_shift_after is None or g - last_shift_after >= min_shift_gap
        ):
            out.append(g)
            last_shift_after = g

    shifts = tuple(out)
    if return_scores:
        return shifts, [float(x) for x in scores.tolist()]
    return shifts

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Literal, cast, overload

import numpy as np
from numpy.typing import NDArray


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer. Returns lowercase tokens."""
    return re.findall(r"[a-zA-Z][a-zA-Z0-9]*", text.lower())


def _scipy_sparse() -> Any | None:
    """Return ``scipy.sparse`` if importable, else ``None`` (dense fallback)."""
    try:
        import scipy.sparse as sp
    except ImportError:
        return None
    return sp


def _vocab_and_idf(
    documents: Sequence[str],
    *,
    max_vocab: int,
    min_df: int,
) -> tuple[list[list[str]], dict[str, int], NDArray[Any]]:
    """Shared front-end: tokenize, pick vocab by document frequency, compute IDF."""
    doc_tokens: list[list[str]] = [_tokenize(d) for d in documents]
    df: dict[str, int] = {}
    for tokens in doc_tokens:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1

    candidates = sorted(
        ((t, c) for t, c in df.items() if c >= min_df),
        key=lambda x: (-x[1], x[0]),
    )
    vocab = [t for t, _ in candidates[:max_vocab]]
    t2i = {t: i for i, t in enumerate(vocab)}
    nd = float(len(documents))
    idf = np.array(
        [np.log((1.0 + nd) / (1.0 + float(df[t]))) + 1.0 for t in vocab],
        dtype=np.float64,
    )
    return doc_tokens, t2i, idf


def _coo_tf(
    doc_tokens: list[list[str]], t2i: dict[str, int]
) -> tuple[list[int], list[int], list[float]]:
    """Build COO (row, col, count) triples of raw term frequencies."""
    counts: dict[tuple[int, int], float] = {}
    for i, tokens in enumerate(doc_tokens):
        for tok in tokens:
            j = t2i.get(tok)
            if j is not None:
                counts[(i, j)] = counts.get((i, j), 0.0) + 1.0
    rows = [r for (r, _c) in counts]
    cols = [c for (_r, c) in counts]
    data = list(counts.values())
    return rows, cols, data


def build_tfidf_matrix(
    documents: Sequence[str],
    *,
    max_vocab: int = 4096,
    min_df: int = 1,
) -> NDArray[Any]:
    """Build a dense, L2-normalized TF-IDF matrix of shape ``(N, V)``.

    API is unchanged from earlier releases: callers always receive a dense
    ``numpy`` array. For large corpora prefer :func:`build_tfidf_sparse`,
    which avoids materializing the (mostly zero) dense matrix.
    """
    n_docs = len(documents)
    if n_docs == 0:
        return np.zeros((0, 1), dtype=np.float64)

    doc_tokens, t2i, idf = _vocab_and_idf(
        documents, max_vocab=max_vocab, min_df=min_df
    )
    v = len(t2i)
    if v == 0:
        return np.zeros((n_docs, 1), dtype=np.float64)

    tf_mat = np.zeros((n_docs, v), dtype=np.float64)
    rows, cols, data = _coo_tf(doc_tokens, t2i)
    if data:
        np.add.at(tf_mat, (np.asarray(rows), np.asarray(cols)), np.asarray(data))

    # TF weighting: (1 + log(tf)) * idf, vectorized over nonzero entries only.
    out = np.zeros_like(tf_mat)
    mask = tf_mat > 0
    out[mask] = 1.0 + np.log(tf_mat[mask])
    out *= idf[None, :]

    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return cast("NDArray[Any]", out / norms)


def build_tfidf_sparse(
    documents: Sequence[str],
    *,
    max_vocab: int = 4096,
    min_df: int = 1,
) -> Any:
    """Build an L2-normalized TF-IDF matrix as a ``scipy.sparse.csr_matrix``.

    Logically identical to :func:`build_tfidf_matrix` but stores only nonzero
    entries, which is dramatically smaller for large documents where each
    sentence touches a tiny slice of the vocabulary.

    Falls back to the dense :func:`build_tfidf_matrix` (returning an
    ``ndarray``) when ``scipy`` is not installed, so callers must accept either
    a CSR matrix or a dense array.
    """
    sp = _scipy_sparse()
    if sp is None:
        return build_tfidf_matrix(documents, max_vocab=max_vocab, min_df=min_df)

    n_docs = len(documents)
    if n_docs == 0:
        return sp.csr_matrix((0, 1), dtype=np.float64)

    doc_tokens, t2i, idf = _vocab_and_idf(
        documents, max_vocab=max_vocab, min_df=min_df
    )
    v = len(t2i)
    if v == 0:
        return sp.csr_matrix((n_docs, 1), dtype=np.float64)

    rows, cols, data = _coo_tf(doc_tokens, t2i)
    tf = sp.coo_matrix(
        (np.asarray(data, dtype=np.float64), (np.asarray(rows), np.asarray(cols))),
        shape=(n_docs, v),
    ).tocsr()

    # (1 + log(tf)) on stored entries, then scale columns by idf.
    weighted = tf.copy()
    weighted.data = 1.0 + np.log(weighted.data)
    weighted = weighted @ sp.diags(idf)

    norms = np.sqrt(weighted.multiply(weighted).sum(axis=1))
    norms = np.asarray(norms).reshape(-1)
    norms[norms == 0] = 1.0
    inv = sp.diags(1.0 / norms)
    return (inv @ weighted).tocsr()


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

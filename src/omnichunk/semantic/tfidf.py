from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer. Returns lowercase tokens."""
    return re.findall(r"[a-zA-Z][a-zA-Z0-9]*", text.lower())


def build_tfidf_matrix(
    documents: Sequence[str],
    *,
    max_vocab: int = 4096,
    min_df: int = 1,
) -> np.ndarray:
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
    out = out / norms
    return out


def detect_topic_shifts(
    sentences: Sequence[str],
    *,
    window: int = 5,
    threshold: float = 0.5,
    min_shift_gap: int = 3,
    max_vocab: int = 2048,
) -> tuple[int, ...]:
    """Detect topic shifts using TF-IDF cosine similarity over sliding windows."""
    n = len(sentences)
    w = int(window)
    if n < 2 * w:
        return ()

    last_shift_after: int | None = None
    out: list[int] = []

    for i in range(w, n - w + 1):
        before = "".join(sentences[i - w : i])
        after = "".join(sentences[i : i + w])
        mat = build_tfidf_matrix([before, after], max_vocab=max_vocab)
        if mat.shape[1] == 0:
            sim = 0.0
        else:
            v0, v1 = mat[0], mat[1]
            denom = float(np.linalg.norm(v0) * np.linalg.norm(v1))
            sim = float(np.dot(v0, v1) / denom) if denom > 0 else 0.0

        boundary_after = i - 1
        if sim < threshold and (
            last_shift_after is None
            or boundary_after - last_shift_after >= min_shift_gap
        ):
            out.append(boundary_after)
            last_shift_after = boundary_after

    return tuple(out)

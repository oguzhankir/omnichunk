"""First-party local sentence embedding via ``sentence-transformers``.

Optional integration: install with ``pip install omnichunk[sentence-transformers]``.
The model is constructed lazily on the first embed call and cached on the
embedder object, so importing this module (or building an embedder) is cheap.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

_INSTALL_HINT = (
    "get_local_embedder requires the 'sentence-transformers' package. "
    "Install it with: pip install 'omnichunk[sentence-transformers]'"
)


def _import_sentence_transformers() -> Any:
    try:
        import sentence_transformers as st
    except ImportError as exc:  # pragma: no cover - exercised via mock injection
        raise ImportError(_INSTALL_HINT) from exc
    return st


class _LocalEmbedder:
    """Callable that embeds ``list[str]`` into a 2D float array.

    Compatible with ``Chunker.semantic_chunk(embed_fn=...)``. The underlying
    SentenceTransformer model loads on first call and is reused thereafter.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any | None = None

    def _model_or_load(self) -> Any:
        if self._model is None:
            st = _import_sentence_transformers()
            self._model = st.SentenceTransformer(self.model_name)
        return self._model

    def __call__(self, texts: Sequence[str]) -> NDArray[Any]:
        model = self._model_or_load()
        embeddings = model.encode(list(texts), convert_to_numpy=True)
        return np.asarray(embeddings, dtype=np.float64)


def get_local_embedder(
    model_name: str = "all-MiniLM-L6-v2",
) -> Callable[[list[str]], NDArray[Any]]:
    """Return an embed function backed by a local sentence-transformers model.

    Raises :class:`ImportError` with an install hint if the optional extra is
    not present. The model itself is loaded lazily on the first embed call.

    Example::

        from omnichunk.semantic.embedders import get_local_embedder

        embed = get_local_embedder()
        chunks = chunker.semantic_chunk("doc.md", text, embed_fn=embed)
    """
    _import_sentence_transformers()  # fail loud now if the extra is missing
    return _LocalEmbedder(model_name)

"""Optional semantic helpers, imported lazily to keep the core lightweight."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "SemanticBoundaryResult": "boundaries",
    "SemanticSplitter": "splitter",
    "build_tfidf_matrix": "tfidf",
    "build_tfidf_sparse": "tfidf",
    "detect_semantic_boundaries": "boundaries",
    "detect_topic_shifts": "tfidf",
    "rerank_chunks": "rerank",
    "split_sentences": "sentences",
}
__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        value = getattr(import_module(f"{__name__}.{module_name}"), name)
    except ModuleNotFoundError as exc:
        if exc.name == "numpy":
            raise ImportError("Semantic helpers require pip install 'omnichunk[semantic]'") from exc
        raise
    globals()[name] = value
    return value

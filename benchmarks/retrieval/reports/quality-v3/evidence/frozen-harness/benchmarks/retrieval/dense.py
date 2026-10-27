"""Offline cosine retrieval from a frozen, source-bound embedding artifact.

Artifacts identify exact UTF-8 inputs and distinguish query/document encoders.
They record the producer's model and preprocessing revisions; hashes cannot
prove that an external producer actually used that model or avoided truncation.
The producer must reject overflow rather than silently truncate an input.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .adapters import Passage

_FIELDS = {
    "schema_version",
    "corpus_manifest_sha256",
    "model_id",
    "model_revision",
    "preprocessing_revision",
    "dimension",
    "overflow_policy",
    "records",
    "producer_metadata",
}


def text_sha256(text: str) -> str:
    """Hash exactly the text delivered to the role-specific encoder."""
    if not isinstance(text, str):
        raise ValueError("Embedding text must be a string")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value.strip() != value:
        raise ValueError(f"{label} must be a nonempty canonical string")
    return value


def _revision(value: Any, label: str) -> str:
    value = _name(value, label)
    if value.casefold() in {"main", "master", "latest", "head"}:
        raise ValueError(f"{label} must identify a frozen revision, not a mutable alias")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"Duplicate embedding artifact field: {key}")
        output[key] = value
    return output


def _vector(value: Any, dimension: int) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != dimension:
        raise ValueError("Embedding vector dimension differs from the artifact dimension")
    try:
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
            raise ValueError("Embedding vectors must contain finite numbers, excluding booleans")
        numbers = tuple(float(x) for x in value)
    except OverflowError as exc:
        raise ValueError("Embedding numbers must be representable as finite floats") from exc
    scale = max(abs(x) for x in numbers)
    if not scale:
        raise ValueError("Embedding vectors must be nonzero")
    # Scale first so even finite vectors near the float maximum normalize safely.
    scaled = tuple(x / scale for x in numbers)
    norm = math.hypot(*scaled)
    return tuple(x / norm for x in scaled)


def _validate(data: Any) -> tuple[dict[str, Any], dict[tuple[str, str], tuple[float, ...]]]:
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise ValueError("Embedding artifact fields do not match schema version 1")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported embedding artifact schema version")
    _digest(data["corpus_manifest_sha256"], "corpus_manifest_sha256")
    _name(data["model_id"], "model_id")
    _revision(data["model_revision"], "model_revision")
    _revision(data["preprocessing_revision"], "preprocessing_revision")
    dimension = data["dimension"]
    if type(dimension) is not int or dimension < 1:
        raise ValueError("Embedding dimension must be a positive integer")
    if data["overflow_policy"] != "error":
        raise ValueError("Embedding producers must declare overflow_policy='error'")
    if not isinstance(data["producer_metadata"], dict):
        raise ValueError("producer_metadata must be a JSON object")
    try:
        json.dumps(data["producer_metadata"], allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("producer_metadata must contain finite JSON values") from exc
    if not isinstance(data["records"], list) or not data["records"]:
        raise ValueError("Embedding artifact records must be a nonempty list")
    vectors: dict[tuple[str, str], tuple[float, ...]] = {}
    for record in data["records"]:
        if not isinstance(record, dict) or set(record) != {"role", "text_sha256", "vector"}:
            raise ValueError("Invalid embedding record fields")
        role = record["role"]
        if role not in ("query", "passage"):
            raise ValueError("Embedding role must be query or passage")
        key = (role, _digest(record["text_sha256"], "text_sha256"))
        if key in vectors:
            raise ValueError("Duplicate embedding role/text digest")
        vectors[key] = _vector(record["vector"], dimension)
    metadata = {key: value for key, value in data.items() if key != "records"}
    metadata["records"] = len(vectors)
    return metadata, vectors


class FrozenDenseRetriever:
    """Load frozen vectors once; never call an embedding provider during evaluation."""

    embedding_calls = 0

    def __init__(
        self,
        path: str | Path,
        *,
        corpus_manifest_sha256: str,
        model_id: str | None = None,
        model_revision: str | None = None,
        preprocessing_revision: str | None = None,
    ) -> None:
        raw = Path(path).read_bytes()
        data = json.loads(raw, object_pairs_hook=_pairs)
        metadata, vectors = _validate(data)
        expected = {
            "corpus_manifest_sha256": _digest(corpus_manifest_sha256, "corpus_manifest_sha256"),
            "model_id": model_id,
            "model_revision": model_revision,
            "preprocessing_revision": preprocessing_revision,
        }
        for key, value in expected.items():
            if value is not None and metadata[key] != value:
                raise ValueError(f"Embedding artifact {key} does not match the experiment")
        metadata["artifact_sha256"] = hashlib.sha256(raw).hexdigest()
        metadata["metric"] = "cosine"
        self._metadata = metadata
        self.vectors: Mapping[tuple[str, str], tuple[float, ...]] = MappingProxyType(vectors)

    @property
    def metadata(self) -> dict[str, Any]:
        return deepcopy(self._metadata)

    def _vector(self, role: str, text: str) -> tuple[float, ...]:
        key = (role, text_sha256(text))
        try:
            return self.vectors[key]
        except KeyError as exc:
            raise ValueError(f"Missing frozen embedding for {role} text SHA-256 {key[1]}") from exc

    def index(self, passages: Sequence[Passage]) -> DensePassageIndex:
        return DensePassageIndex(self, passages)


class DensePassageIndex:
    def __init__(self, retriever: FrozenDenseRetriever, passages: Sequence[Passage]) -> None:
        ids = [passage.passage_id for passage in passages]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate passage IDs in dense index")
        self.retriever = retriever
        self.passages = [
            (passage, retriever._vector("passage", passage.text)) for passage in passages
        ]

    def rank(self, query: str) -> list[tuple[Passage, float]]:
        vector = self.retriever._vector("query", query)
        ranked = [
            (passage, max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(vector, candidate)))))
            for passage, candidate in self.passages
        ]
        return sorted(ranked, key=lambda item: (-item[1], item[0].passage_id))


def build_dense_artifact(
    path: str | Path,
    *,
    corpus_manifest_sha256: str,
    model_id: str,
    model_revision: str,
    preprocessing_revision: str,
    passages: Sequence[str],
    queries: Sequence[str],
    embed: Callable[[str, Sequence[str]], Sequence[Sequence[float]]],
    batch_size: int = 64,
    producer_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare an artifact with a caller-owned, overflow-rejecting encoder.

    The callback receives a role and exact input strings. It must preserve their
    order and return one vector per string. No provider or model is selected here.
    An invalid/failed batch never replaces an existing artifact.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("Embedding batch_size must be a positive integer")
    data: dict[str, Any] = {
        "schema_version": 1,
        "corpus_manifest_sha256": _digest(corpus_manifest_sha256, "corpus_manifest_sha256"),
        "model_id": _name(model_id, "model_id"),
        "model_revision": _revision(model_revision, "model_revision"),
        "preprocessing_revision": _revision(preprocessing_revision, "preprocessing_revision"),
        "dimension": None,
        "overflow_policy": "error",
        "producer_metadata": producer_metadata or {},
        "records": [],
    }
    calls = 0
    for role, texts in (("passage", passages), ("query", queries)):
        unique = {text_sha256(text): text for text in texts}
        ordered = sorted(unique.items())
        for start in range(0, len(ordered), batch_size):
            batch = ordered[start : start + batch_size]
            vectors = list(embed(role, [text for _, text in batch]))
            calls += 1
            if len(vectors) != len(batch):
                raise ValueError("Embedding callback returned the wrong number of vectors")
            for (digest, _), vector in zip(batch, vectors):
                if data["dimension"] is None:
                    data["dimension"] = len(vector)
                # Validate before converting to JSON-compatible lists.
                _vector(vector, data["dimension"])
                data["records"].append(
                    {"role": role, "text_sha256": digest, "vector": list(vector)}
                )
    metadata, _ = _validate(data)
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {
        **metadata,
        "artifact_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "embedding_calls": calls,
    }

"""External frozen-vector extension; never modifies the benchmark harness.

Reuse trusted prior records only by exact (encoder role, UTF-8 text SHA-256).
Validate every requested full model input; encode only cache misses. The produced
artifact contains candidate-required records, not unrelated baseline records.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

PACKAGES = ("sentence-transformers", "transformers", "torch", "tokenizers")
INPUT_POLICY = "full tokenizer inputs including special tokens; reject overflow"
PIPELINE = "standard Transformer + mean Pooling (+ Normalize); no prompts"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def package_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in PACKAGES}


def load_api(harness: Path, runtime: Path) -> Any:
    sys.path[:0] = [str(runtime.resolve() / "src"), str(harness.resolve())]
    from benchmarks import prepare_dense
    from benchmarks.retrieval import adapters, corpus, dense, tokenization

    for module in (prepare_dense, adapters, corpus, dense, tokenization):
        if not Path(module.__file__).resolve().is_relative_to(harness.resolve()):
            raise ValueError("Benchmark module did not load from the frozen harness")
    import omnichunk

    if not Path(omnichunk.__file__).resolve().is_relative_to(runtime.resolve() / "src"):
        raise ValueError("Runtime did not load from the declared checkout")
    return argparse.Namespace(
        prepare=prepare_dense,
        adapters=adapters,
        corpus=corpus,
        dense=dense,
        tokenization=tokenization,
    )


def read_prior(path: Path, expected_sha: str, api: Any) -> dict[str, Any]:
    raw = path.read_bytes()
    if sha256(raw) != expected_sha:
        raise ValueError("Prior artifact SHA-256 does not match the commitment")
    decoded = gzip.decompress(raw) if path.suffix == ".gz" else raw
    data = json.loads(decoded, object_pairs_hook=api.dense._pairs)
    api.dense._validate(data)
    return data


def validate_prior(
    data: dict[str, Any],
    *,
    corpus_sha: str,
    model_id: str,
    model_revision: str,
    preprocessing_revision: str,
    files: dict[str, str],
    packages: dict[str, str],
    producer_sha: str,
    limit: int,
    threads: int = 2,
) -> None:
    expected = {
        "corpus_manifest_sha256": corpus_sha,
        "model_id": model_id,
        "model_revision": model_revision,
        "preprocessing_revision": preprocessing_revision,
        "overflow_policy": "error",
    }
    for field, value in expected.items():
        if data.get(field) != value:
            raise ValueError(f"Prior artifact {field} differs from the declared experiment")
    metadata = data["producer_metadata"]
    expected_metadata = {
        "model_files": files,
        "packages": packages,
        "prompt": "",
        "include_special_tokens": True,
        "max_sequence_length": limit,
        "input_policy": INPUT_POLICY,
        "supported_pipeline": PIPELINE,
        "normalization": "cosine normalization during evaluation",
        "device": "cpu",
        "producer_source_sha256": producer_sha,
        "cpu_threads_requested": threads,
        "torch_threads": {"intraop": threads, "interop": threads},
    }
    for field, value in expected_metadata.items():
        if metadata.get(field) != value or type(metadata.get(field)) is not type(value):
            raise ValueError(f"Prior producer metadata {field} differs from the frozen producer")
    statistics = metadata.get("input_statistics", {})
    maximum = statistics.get("maximum_input_tokens")
    if type(maximum) is not int or not 1 <= maximum <= limit:
        raise ValueError("Prior full-input token statistics contradict the overflow policy")
    if statistics.get("encoded_texts") != len(data["records"]):
        raise ValueError("Prior encoded-text cardinality differs from stored role records")
    for role in ("passage", "query"):
        count = sum(record["role"] == role for record in data["records"])
        stats = metadata.get("role_statistics", {}).get(role, {})
        if not count or stats.get("unique_texts") != count:
            raise ValueError(f"Prior {role} role/cardinality contract is missing or inconsistent")


class CachedEncoder:
    def __init__(
        self,
        records: list[dict[str, Any]],
        *,
        model: Any,
        limit: int,
        batch_size: int,
        text_sha: Any,
        metadata: dict[str, Any],
    ) -> None:
        if not records:
            raise ValueError("Prior records must not be empty")
        self.dimension = len(records[0]["vector"])
        self.cache = {(r["role"], r["text_sha256"]): r["vector"] for r in records}
        self.model, self.limit, self.batch_size = model, limit, batch_size
        self.text_sha, self.metadata = text_sha, metadata
        self.tokens: dict[tuple[str, str], int] = {}
        self.reused: dict[tuple[str, str], str] = {}
        self.stats = {
            role: {
                "requested_unique_texts": 0,
                "requested_input_tokens": 0,
                "reused_texts": 0,
                "reused_input_tokens": 0,
                "new_texts": 0,
                "new_input_tokens": 0,
                "encoder_calls": 0,
                "encoder_batch_sizes": [],
                "encoding_seconds": 0.0,
            }
            for role in ("passage", "query")
        }
        self.validation_seconds = 0.0
        self.maximum_input_tokens = 0

    def __call__(self, role: str, texts: Sequence[str]) -> list[list[float]]:
        if role not in self.stats:
            raise ValueError("Encoder role must be passage or query")
        start = perf_counter()
        tokenized = self.model.tokenizer(
            texts, truncation=False, add_special_tokens=True, padding=False
        )
        ids = tokenized["input_ids"]
        lengths = [len(row) for row in ids]
        if len(lengths) != len(texts):
            raise ValueError("Tokenizer did not preserve embedding cardinality")
        if max(lengths, default=0) > self.limit:
            raise ValueError(
                f"{role} input exceeds the full model token limit; truncation forbidden"
            )
        native = self.model.tokenize(list(texts))
        native_ids = native["input_ids"].tolist()
        masks = native["attention_mask"].tolist()
        if len(native_ids) != len(texts) or len(masks) != len(texts):
            raise ValueError("Native model tokenization changed cardinality")
        unpadded = []
        for row, mask in zip(native_ids, masks):
            if len(row) != len(mask) or any(value not in (0, 1) for value in mask):
                raise ValueError("Invalid native attention mask")
            unpadded.append([token for token, keep in zip(row, mask) if keep])
        if unpadded != ids:
            raise ValueError("Native model preprocessing changes or truncates full input token IDs")
        self.validation_seconds += perf_counter() - start
        self.maximum_input_tokens = max(self.maximum_input_tokens, max(lengths, default=0))
        stats = self.stats[role]
        stats["requested_unique_texts"] += len(texts)
        stats["requested_input_tokens"] += sum(lengths)
        output: list[Any] = [None] * len(texts)
        missing = []
        for position, (text, size) in enumerate(zip(texts, lengths)):
            key = role, self.text_sha(text)
            self.tokens[key] = size
            if key in self.cache:
                vector = self.cache[key]
                output[position] = vector
                self.reused[key] = sha256(
                    json.dumps(vector, allow_nan=False, separators=(",", ":")).encode()
                )
                stats["reused_texts"] += 1
                stats["reused_input_tokens"] += size
            else:
                missing.append(position)
                stats["new_texts"] += 1
                stats["new_input_tokens"] += size
        if missing:
            start = perf_counter()
            encoded = self.model.encode(
                [texts[i] for i in missing],
                batch_size=self.batch_size,
                prompt="",
                normalize_embeddings=False,
                convert_to_numpy=True,
                show_progress_bar=False,
            ).tolist()
            if len(encoded) != len(missing):
                raise ValueError("Encoder did not preserve missing-input cardinality")
            stats["encoding_seconds"] += perf_counter() - start
            stats["encoder_calls"] += 1
            stats["encoder_batch_sizes"].append(len(missing))
            for position, vector in zip(missing, encoded):
                output[position] = vector
        if any(len(vector) != self.dimension for vector in output):
            raise ValueError("Encoded vector dimension differs from the trusted prior/model")
        self.metadata["actual_encoder_work"] = self.stats
        self.metadata["token_validation_seconds"] = self.validation_seconds
        self.metadata["maximum_input_tokens"] = self.maximum_input_tokens
        return output


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    api = load_api(args.harness_root, args.runtime_root)
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing experiment artifact")
    api.prepare._configure_cpu_threads(args.cpu_threads)
    started = perf_counter()
    files = api.prepare.model_files(args.model_dir)
    packages = package_versions()
    producer_sha = sha256(Path(api.prepare.__file__).read_bytes())
    corpus = api.corpus.load_corpus(args.corpus)
    prior = read_prior(args.prior, args.prior_sha256, api)
    model = api.prepare._load_model(args.model_dir.resolve())
    limit = getattr(model, "max_seq_length", None)
    if type(limit) is not int or limit < 1 or not callable(getattr(model, "tokenizer", None)):
        raise ValueError("Model requires a callable tokenizer and finite positive max_seq_length")
    tokenizer_limit = getattr(model.tokenizer, "model_max_length", limit)
    if type(tokenizer_limit) is int and 0 < tokenizer_limit < limit:
        limit = tokenizer_limit
    validate_prior(
        prior,
        corpus_sha=corpus.manifest_hash,
        model_id=args.model_id,
        model_revision=args.model_revision,
        preprocessing_revision=args.preprocessing_revision,
        files=files,
        packages=packages,
        producer_sha=producer_sha,
        limit=limit,
        threads=args.cpu_threads,
    )
    if model.get_sentence_embedding_dimension() != prior["dimension"]:
        raise ValueError("Prior vector dimension differs from the pinned model")
    initialization_seconds = perf_counter() - started
    counter = api.tokenization.benchmark_counter(
        "tokens", str(args.model_dir), include_special_tokens=True
    )
    candidates = []
    for tool in args.tools.split(","):
        if tool not in api.adapters.TOOLS:
            raise ValueError(f"Unknown frozen adapter: {tool}")
        for capacity in args.chunk_sizes:
            texts = [
                p.text
                for d in corpus.documents
                if d.split == args.split
                for p in api.adapters.split_document(
                    tool, d.source_id, d.path, d.text, capacity, counter, "tokens"
                )
            ]
            candidates.append((tool, capacity, texts))
    passages = [text for _, _, texts in candidates for text in texts]
    queries = [q.text for q in corpus.queries if q.split == args.split]
    if not passages or not queries:
        raise ValueError("Requested split needs both passages and queries")
    metadata: dict[str, Any] = {
        "external_producer_source_sha256": sha256(Path(__file__).read_bytes()),
        "frozen_producer_source_sha256": producer_sha,
        "prior_artifact_sha256": args.prior_sha256,
        "prior_artifact_records": len(prior["records"]),
        "prior_model_files": files,
        "model_files": files,
        "packages": packages,
        "device": "cpu",
        "prompt": "",
        "include_special_tokens": True,
        "max_sequence_length": limit,
        "input_policy": INPUT_POLICY,
        "supported_pipeline": PIPELINE,
        "normalization": "cosine normalization during evaluation",
        "initialization_seconds": initialization_seconds,
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_threads_requested": args.cpu_threads,
        "measurement_scope": "Trusted prior vectors are reused unchanged by exact role/text hash. "
        "Actual encoder work counts only newly encoded inputs; initialization and token validation "
        "are separate. Baseline encoding times are not copied or attributed to these candidates. "
        "Total candidate input workloads are reported independently of actual cache-miss work. "
        "Package versions and model files are checked; complete package-file provenance belongs "
        "to the external frozen-environment audit.",
    }
    encoder = CachedEncoder(
        prior["records"],
        model=model,
        limit=limit,
        batch_size=args.batch_size,
        text_sha=api.dense.text_sha256,
        metadata=metadata,
    )
    # The builder deduplicates and orders exact role inputs. This wrapper checks
    # file stability on its last callback, before the builder atomically writes.
    remaining = sum(
        (len(set(texts)) + args.batch_size - 1) // args.batch_size for texts in (passages, queries)
    )

    def embed(role: str, texts: Sequence[str]) -> list[list[float]]:
        nonlocal remaining
        result = encoder(role, texts)
        remaining -= 1
        if remaining == 0:
            if api.prepare.model_files(args.model_dir) != files or package_versions() != packages:
                raise ValueError(
                    "Pinned model files or package versions changed during preparation"
                )
            metadata["candidate_workloads"] = [
                {
                    "tool": tool,
                    "chunk_capacity": capacity,
                    "passages": len(texts),
                    "unique_passage_payloads": len(set(texts)),
                    "duplicate_payload_reuses": len(texts) - len(set(texts)),
                    "passage_input_tokens": sum(
                        encoder.tokens["passage", api.dense.text_sha256(t)] for t in texts
                    ),
                    "unique_passage_input_tokens": sum(
                        encoder.tokens["passage", api.dense.text_sha256(t)] for t in set(texts)
                    ),
                }
                for tool, capacity, texts in candidates
            ]
            metadata["reused_vector_payloads_sha256"] = sha256(
                json.dumps(
                    sorted(
                        (role, digest, value) for (role, digest), value in encoder.reused.items()
                    ),
                    separators=(",", ":"),
                ).encode()
            )
        return result

    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".extension-", dir=args.output.parent)
    os.close(descriptor)
    staging = Path(name)
    try:
        result = api.dense.build_dense_artifact(
            staging,
            corpus_manifest_sha256=corpus.manifest_hash,
            model_id=args.model_id,
            model_revision=args.model_revision,
            preprocessing_revision=args.preprocessing_revision,
            passages=passages,
            queries=queries,
            embed=embed,
            batch_size=args.batch_size,
            producer_metadata=metadata,
        )
        callback_batches = result.pop("embedding_calls")
        artifact = json.loads(staging.read_text(), object_pairs_hook=api.dense._pairs)
        if artifact["dimension"] != prior["dimension"]:
            raise ValueError("Extended artifact dimension differs from the trusted prior/model")
        for record in artifact["records"]:
            key = record["role"], record["text_sha256"]
            if key in encoder.reused:
                actual = sha256(
                    json.dumps(record["vector"], allow_nan=False, separators=(",", ":")).encode()
                )
                if actual != encoder.reused[key]:
                    raise ValueError("Reused vector payload changed during artifact serialization")
        os.link(staging, args.output)  # atomic publication; refuse any existing destination
    finally:
        staging.unlink(missing_ok=True)
    result["artifact_builder_callback_batches"] = callback_batches
    result["actual_encoder_work"] = encoder.stats
    return result


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("harness-root", "runtime-root", "corpus", "model-dir", "prior", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("prior-sha256", "model-id", "model-revision"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--preprocessing-revision", default="sentence-transformers-no-prompt-v1")
    p.add_argument("--split", choices=["dev", "test"], required=True)
    p.add_argument("--tools", required=True)
    p.add_argument("--chunk-sizes", type=int, nargs="+", default=[64, 96])
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--cpu-threads", type=int, default=2)
    args = p.parse_args()
    if min(args.batch_size, args.cpu_threads, *args.chunk_sizes) < 1:
        p.error("Batch, thread and chunk sizes must be positive")
    print(json.dumps(prepare(args), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

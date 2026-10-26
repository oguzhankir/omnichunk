"""Prepare frozen retrieval embeddings using an explicitly cached local model.

No model is selected or downloaded automatically. Install sentence-transformers
separately, prefetch a pinned model snapshot, and pass its directory and revision.
The built-in producer supports symmetric Transformer + mean Pooling models,
optionally followed by Normalize, with no prompts or custom preprocessing.
Use build_dense_artifact with an explicit external encoder for asymmetric models.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.retrieval.adapters import TOOLS, split_document  # noqa: E402
from benchmarks.retrieval.corpus import load_corpus  # noqa: E402
from benchmarks.retrieval.dense import build_dense_artifact  # noqa: E402
from benchmarks.retrieval.tokenization import benchmark_counter  # noqa: E402


def _peak_rss_bytes() -> int | None:
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)
    except ImportError:
        return None


def model_files(directory: Path) -> dict[str, str]:
    """Fingerprint every snapshot file, including weights and tokenizer settings."""
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            result[path.relative_to(directory).as_posix()] = digest.hexdigest()
    if not result:
        raise ValueError("The local model directory contains no files")
    return result


def _load_model(directory: Path) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
        from sentence_transformers.models import Normalize, Pooling, Transformer
    except ImportError as exc:
        raise ImportError(
            "Install sentence-transformers to prepare local dense embeddings"
        ) from exc
    model = SentenceTransformer(
        str(directory), device="cpu", local_files_only=True, trust_remote_code=False
    )
    modules = list(model.children())
    if (
        len(modules) not in (2, 3)
        or type(modules[0]) is not Transformer
        or type(modules[1]) is not Pooling
        or (len(modules) == 3 and type(modules[2]) is not Normalize)
    ):
        raise ValueError(
            "Only standard Transformer + mean Pooling (+ Normalize) models are supported"
        )
    pooling = modules[1]
    pooling_config = pooling.get_config_dict()
    modes = ("cls_token", "max_tokens", "mean_sqrt_len_tokens", "weightedmean_tokens", "lasttoken")
    mean_only = pooling_config.get("pooling_mode") == "mean" or (
        pooling_config.get("pooling_mode_mean_tokens") is True
        and not any(pooling_config.get(f"pooling_mode_{mode}", False) for mode in modes)
    )
    if not mean_only:
        raise ValueError("Only mean-only pooling is supported by this producer")
    if any(getattr(model, "prompts", {}).values()) or getattr(model, "default_prompt_name", None):
        raise ValueError(
            "Prompt-configured models require a separate explicit role-specific producer"
        )
    return model


def _configure_cpu_threads(threads: int | None) -> None:
    """Set both process-global Torch pools before any model work, when requested."""
    if threads is None:
        return
    if type(threads) is not int or threads < 1:
        raise ValueError("--cpu-threads must be a positive integer")
    try:
        import torch
    except ImportError as exc:
        raise ImportError("Install torch to configure --cpu-threads for dense preparation") from exc
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(threads)


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    directory = args.model_dir.resolve()
    if not directory.is_dir():
        raise ValueError("--model-dir must be an existing local model snapshot directory")
    _configure_cpu_threads(getattr(args, "cpu_threads", None))
    started = perf_counter()
    files = model_files(directory)
    snapshot_hash_seconds = perf_counter() - started
    corpus = load_corpus(args.corpus)
    counter = benchmark_counter(
        args.unit,
        args.tokenizer,
        include_special_tokens=getattr(args, "include_special_tokens", False),
    )
    candidate_texts = []
    for tool in args.tools.split(","):
        for size in args.chunk_sizes:
            texts = [
                passage.text
                for document in corpus.documents
                if document.split == args.split
                for passage in split_document(
                    tool, document.source_id, document.path, document.text, size, counter, args.unit
                )
            ]
            candidate_texts.append((tool, size, texts))
    passages = [text for _, _, texts in candidate_texts for text in texts]
    queries = [query.text for query in corpus.queries if query.split == args.split]
    if not passages or not queries:
        raise ValueError("Selected corpus split must contain passages and queries")
    started = perf_counter()
    model = _load_model(directory)
    model_load_seconds = perf_counter() - started
    limit = getattr(model, "max_seq_length", None)
    tokenizer = getattr(model, "tokenizer", None)
    if type(limit) is not int or limit < 1 or not callable(tokenizer):
        raise ValueError("Model must expose a tokenizer and a finite positive max_seq_length")
    tokenizer_limit = getattr(tokenizer, "model_max_length", limit)
    if isinstance(tokenizer_limit, int) and 0 < tokenizer_limit < limit:
        limit = tokenizer_limit
    counts = {"maximum_input_tokens": 0, "encoded_texts": 0}
    timings = {
        "snapshot_hash_seconds": snapshot_hash_seconds,
        "model_load_seconds": model_load_seconds,
        "token_validation_seconds": 0.0,
        "encoding_seconds": 0.0,
        "process_lifetime_peak_rss_before_serialization_bytes": None,
    }
    role_statistics = {
        role: {"batches": 0, "unique_texts": 0, "input_tokens": 0, "encoding_seconds": 0.0}
        for role in ("passage", "query")
    }
    token_counts: dict[str, int] = {}
    candidate_workloads: list[dict[str, Any]] = []
    remaining_batches = sum(
        (len(set(texts)) + args.batch_size - 1) // args.batch_size for texts in (passages, queries)
    )

    def embed(role: str, texts: Sequence[str]) -> list[list[float]]:
        nonlocal remaining_batches
        started = perf_counter()
        # Explicit empty prompt prevents model defaults from changing the input
        # after overflow checking. Query/passage roles still have separate keys.
        tokenized = tokenizer(texts, truncation=False, add_special_tokens=True, padding=False)
        lengths = [len(ids) for ids in tokenized["input_ids"]]
        if len(lengths) != len(texts):
            raise ValueError("Tokenizer did not preserve embedding batch cardinality")
        largest = max(lengths, default=0)
        if largest > limit:
            raise ValueError(
                f"Dense {role} input requires {largest} model tokens; limit is {limit}. "
                "Reduce chunk sizes; truncated comparisons are forbidden."
            )
        native = model.tokenize(list(texts))
        native_ids = native["input_ids"].tolist()
        native_masks = native["attention_mask"].tolist()
        if len(native_ids) != len(texts) or len(native_masks) != len(texts):
            raise ValueError("Native model tokenization changed input cardinality")
        unpadded = []
        for ids, mask in zip(native_ids, native_masks):
            if len(ids) != len(mask) or any(value not in (0, 1) for value in mask):
                raise ValueError("Native model tokenization returned an invalid attention mask")
            unpadded.append([token for token, keep in zip(ids, mask) if keep])
        if unpadded != tokenized["input_ids"]:
            raise ValueError(
                "Native model preprocessing changes or truncates inputs; "
                "this producer only supports identical full tokenizer inputs"
            )
        timings["token_validation_seconds"] += perf_counter() - started
        counts["maximum_input_tokens"] = max(counts["maximum_input_tokens"], largest)
        counts["encoded_texts"] += len(texts)
        if role == "passage":
            token_counts.update(zip(texts, lengths))
        started = perf_counter()
        encoded = model.encode(
            list(texts),
            batch_size=args.batch_size,
            prompt="",
            normalize_embeddings=False,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        elapsed = perf_counter() - started
        timings["encoding_seconds"] += elapsed
        role_statistics[role]["batches"] += 1
        role_statistics[role]["unique_texts"] += len(texts)
        role_statistics[role]["input_tokens"] += sum(lengths)
        role_statistics[role]["encoding_seconds"] += elapsed
        remaining_batches -= 1
        if remaining_batches == 0:
            if model_files(directory) != files:
                raise ValueError("Local model files changed while encoding inputs")
            for tool, size, payloads in candidate_texts:
                unique = set(payloads)
                candidate_workloads.append(
                    {
                        "tool": tool,
                        "chunk_capacity": size,
                        "passages": len(payloads),
                        "unique_passage_payloads": len(unique),
                        "duplicate_payload_reuses": len(payloads) - len(unique),
                        "passage_input_tokens": sum(token_counts[text] for text in payloads),
                        "unique_passage_input_tokens": sum(token_counts[text] for text in unique),
                    }
                )
            timings["process_lifetime_peak_rss_before_serialization_bytes"] = _peak_rss_bytes()
        return encoded.tolist()

    versions = {}
    for package in ("sentence-transformers", "transformers", "torch", "tokenizers"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    metadata = {
        "model_files": files,
        "producer_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "packages": versions,
        "device": "cpu",
        "cpu_threads_requested": getattr(args, "cpu_threads", None),
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "prompt": "",
        "include_special_tokens": getattr(args, "include_special_tokens", False),
        "max_sequence_length": limit,
        "input_policy": "full tokenizer inputs including special tokens; reject overflow",
        "supported_pipeline": "standard Transformer + mean Pooling (+ Normalize); no prompts",
        "normalization": "cosine normalization during evaluation",
        "input_statistics": counts,
        "torch_threads": {
            name: getattr(sys.modules.get("torch"), method, lambda: None)()
            for name, method in (
                ("intraop", "get_num_threads"),
                ("interop", "get_num_interop_threads"),
            )
        },
        "timings": timings,
        "role_statistics": role_statistics,
        "candidate_workloads": candidate_workloads,
        "measurement_scope": (
            "One shared preparation pass, deduplicated within each encoder role across "
            "all candidates. Encoding times include the first model call and native batching; "
            "they are not isolated per-candidate cold-start or online query latency. "
            "Candidate token workloads count complete model inputs including special tokens."
            " RSS is process-lifetime high-water memory before artifact serialization, "
            "not an isolated per-candidate encoder peak."
        ),
    }
    # Loading or encoding must not change the pinned snapshot. The final batch
    # checks again before the artifact builder can replace its output file.
    if model_files(directory) != files:
        raise ValueError("Local model files changed during initialization")
    result = build_dense_artifact(
        args.output,
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
    return {**result, **counts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "benchmarks/retrieval/corpus_v1")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--tools", default="omnichunk,fixed")
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=[128, 256])
    parser.add_argument("--unit", choices=["chars", "tokens"], default="chars")
    parser.add_argument("--tokenizer", default="cl100k_base")
    parser.add_argument(
        "--include-special-tokens",
        action="store_true",
        help="Count full model inputs using an explicitly local Hugging Face tokenizer",
    )
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--preprocessing-revision", default="sentence-transformers-no-prompt-v1")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--cpu-threads",
        type=int,
        help="Set both Torch CPU thread pools once before loading the model",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if any(n < 1 for n in [*args.chunk_sizes, args.batch_size]):
        parser.error("Chunk sizes and batch size must be positive")
    if args.cpu_threads is not None and args.cpu_threads < 1:
        parser.error("--cpu-threads must be a positive integer")
    if any(tool not in TOOLS for tool in args.tools.split(",")):
        parser.error(f"--tools must select names from {', '.join(TOOLS)}")
    if args.unit == "tokens" and args.tokenizer == "approximate":
        parser.error("Dense comparisons require an exact tokenizer")
    try:
        result = prepare(args)
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        print(f"Dense preparation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

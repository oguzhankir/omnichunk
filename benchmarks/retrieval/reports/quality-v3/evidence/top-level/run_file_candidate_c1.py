"""Supplemental development file-view candidate run; no source or tuning changes."""

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

W = Path("/workspace/work/omnichunk-v3")
H = W / "frozen-candidate-v2"
CORPUS = W / "code-files/development"
MODELS = [
    (
        "multilingual",
        Path("/workspace/work/omnichunk-dense/model-path.txt").read_text().strip(),
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
    ),
    (
        "english",
        Path("/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt")
        .read_text()
        .strip(),
        "sentence-transformers/all-MiniLM-L6-v2",
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    ),
]
TOOLS = "omnichunk,omnichunk-prose-compact,omnichunk-code-compact"


def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def run(args, out, name, env):
    with (out / name).open("w") as f:
        subprocess.run(
            [sys.executable, *args], cwd=H, env=env, stdout=f, stderr=subprocess.STDOUT, check=True
        )


def compress(p):
    with (
        p.open("rb") as src,
        p.with_suffix(p.suffix + ".gz").open("wb") as raw,
        gzip.GzipFile(fileobj=raw, filename="", mtime=0, mode="wb") as target,
    ):
        shutil.copyfileobj(src, target)
    p.unlink()


assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=H, text=True).strip()
rev = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=H, text=True).strip()
assert rev.startswith("c1d2186")
for label, model, model_id, model_sha in MODELS:
    out = W / f"dev/code-files/{label}/candidate-final-c1"
    out.mkdir(parents=True)
    prior = W / f"dev/code-files/{label}/baseline/vectors.json.gz"
    vectors = out / "vectors.json"
    report = out / "report.json"
    env = {
        **os.environ,
        "PYTHONPATH": str(H / "src"),
        "OMP_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTHONHASHSEED": "0",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "NLTK_DATA": str(W / "adapter-audit/nltk_data"),
    }
    manifest = {
        "development_only": True,
        "supplemental_correlated_view": "real original files, same questions; no new selection",
        "runtime": rev,
        "harness_root": str(H),
        "corpus_sha256": digest(CORPUS / "manifest.json"),
        "model": model_id,
        "revision": model_sha,
        "tools": TOOLS,
        "native_chunk_capacities": [64, 96],
        "primary_context_budget": 512,
        "split": "dev",
        "cache_prior": str(prior),
        "cache_prior_sha256": digest(prior),
        "external_producer_sha256": digest(W / "extend_dense_vectors.py"),
    }
    (out / "job.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(label, "candidate cache preparation started", flush=True)
    run(
        [
            str(W / "extend_dense_vectors.py"),
            "--harness-root",
            str(H),
            "--runtime-root",
            str(H),
            "--corpus",
            str(CORPUS),
            "--model-dir",
            model,
            "--model-id",
            model_id,
            "--model-revision",
            model_sha,
            "--prior",
            str(prior),
            "--prior-sha256",
            manifest["cache_prior_sha256"],
            "--split",
            "dev",
            "--tools",
            TOOLS,
            "--chunk-sizes",
            "64",
            "96",
            "--cpu-threads",
            "2",
            "--batch-size",
            "32",
            "--output",
            str(vectors),
        ],
        out,
        "prepare.log",
        env,
    )
    print(label, "candidate primary evaluation started", flush=True)
    run(
        [
            str(H / "benchmarks/run_retrieval.py"),
            "--corpus",
            str(CORPUS),
            "--split",
            "dev",
            "--tools",
            TOOLS,
            "--chunk-sizes",
            "64",
            "96",
            "--unit",
            "tokens",
            "--tokenizer",
            model,
            "--include-special-tokens",
            "--retriever",
            "dense",
            "--dense-embeddings",
            str(vectors),
            "--retrieval-budget",
            "512",
            "--top-k",
            "5",
            "--repeats",
            "3",
            "--require-all",
            "--output",
            str(report),
        ],
        out,
        "evaluate.log",
        env,
    )
    data = json.loads(report.read_text())
    assert (
        data["environment"]["runtime_git_revision"] == rev
        and not data["environment"]["runtime_git_dirty"]
    )
    assert all(c["status"] == "ok" for c in data["candidates"])
    print(label, "candidate primary complete", flush=True)
    for path in [vectors, report]:
        compress(path)

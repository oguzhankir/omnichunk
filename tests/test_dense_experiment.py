from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import pytest

from benchmarks import run_dense_experiment as experiment


def test_manual_workflow_resolves_one_model_commit_before_corpus_matrix():
    yaml = pytest.importorskip("yaml")
    source = (experiment.ROOT / ".github/workflows/dense-evaluation.yml").read_text()
    data = yaml.safe_load(source)
    # PyYAML's YAML 1.1 loader treats the GitHub Actions `on` key as True.
    triggers = data.get("on", data.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    jobs = data["jobs"]
    assert source.count("HfApi().model_info") == 1
    assert jobs["evaluate"]["needs"] == "resolve_model"
    assert jobs["resolve_model"]["outputs"]["revision"] == "${{ steps.model.outputs.revision }}"
    snapshot = next(step for step in jobs["evaluate"]["steps"] if step.get("id") == "snapshot")
    assert snapshot["env"]["MODEL_REVISION"] == "${{ needs.resolve_model.outputs.revision }}"
    assert jobs["evaluate"]["strategy"]["matrix"]["corpus"] == [
        "corpus_v1",
        "corpus_squad_v1",
    ]


def configuration(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    baseline = tmp_path / "baseline"
    (baseline / "src/omnichunk").mkdir(parents=True)
    (baseline / "src/omnichunk/__init__.py").write_text("")
    return argparse.Namespace(
        model_dir=model,
        model_id=experiment.MODEL,
        model_revision="a" * 40,
        baseline_dir=baseline,
        output_dir=tmp_path / "results",
        corpus="corpus_v1",
        split="dev",
    )


def test_orchestration_uses_same_harness_model_and_budgets_for_both_runtimes(tmp_path, monkeypatch):
    args = configuration(tmp_path)
    calls = []

    def command(arguments, environment, output):
        calls.append((arguments, environment))
        output.write_text("captured stdout")
        destination = Path(arguments[arguments.index("--output") + 1])
        destination.write_text(json.dumps({"script": arguments[0]}))

    monkeypatch.setattr(experiment, "_command", command)
    manifest = experiment.run(args)
    assert manifest["split"] == "dev"
    assert manifest["include_special_tokens"] is True
    assert manifest["cpu_threads"] == 2
    assert len(calls) == 10
    preparations = [item for item in calls if item[0][0] == "benchmarks/prepare_dense.py"]
    assert [env["PYTHONPATH"] for _, env in preparations] == [
        str(args.baseline_dir / "src"),
        str(experiment.ROOT / "src"),
    ]
    assert all(
        arguments[arguments.index("--cpu-threads") + 1] == "2" for arguments, _ in preparations
    )
    for arguments, environment in calls[:4]:
        assert "--include-special-tokens" in arguments
        assert environment["OMP_NUM_THREADS"] == environment["MKL_NUM_THREADS"] == "2"
        assert arguments[arguments.index("--tokenizer") + 1] == str(args.model_dir)
        assert arguments[arguments.index("--chunk-sizes") + 1 : arguments.index("--unit")] == [
            "64",
            "96",
        ]
    evaluations = [item[0] for item in calls if item[0][0] == "benchmarks/run_retrieval.py"]
    assert len(evaluations) == 2
    assert all(item[item.index("--retrieval-budget") + 1] == "512" for item in evaluations)
    for label in ("baseline", "candidate"):
        assert not (args.output_dir / f"{label}.vectors.json").exists()
        with gzip.open(args.output_dir / f"{label}.vectors.json.gz", "rt") as handle:
            assert json.load(handle)["script"] == "benchmarks/prepare_dense.py"
        assert (args.output_dir / f"{label}.report.json.gz").exists()


@pytest.mark.parametrize("revision", ["main", "resolve", "a" * 39, "z" * 40])
def test_orchestration_rejects_mutable_or_invalid_model_revision_before_calls(
    tmp_path, monkeypatch, revision
):
    args = configuration(tmp_path)
    args.model_revision = revision
    monkeypatch.setattr(
        experiment, "_command", lambda *args: pytest.fail("must not start encoding")
    )
    with pytest.raises(ValueError, match="frozen 40-character"):
        experiment.run(args)
    assert not args.output_dir.exists()


def test_orchestration_preserves_existing_results(tmp_path, monkeypatch):
    args = configuration(tmp_path)
    args.output_dir.mkdir()
    preserved = args.output_dir / "experiment.json"
    preserved.write_text("existing evidence")
    monkeypatch.setattr(experiment, "_command", lambda *args: pytest.fail("must not overwrite"))
    with pytest.raises(ValueError, match="preserve prior"):
        experiment.run(args)
    assert preserved.read_text() == "existing evidence"


def test_external_corpus_candidate_checkout_and_extended_strategies_are_forwarded(
    tmp_path, monkeypatch
):
    args = configuration(tmp_path)
    corpus = tmp_path / "external-corpus"
    corpus.mkdir()
    (corpus / "manifest.json").write_text("{}")
    args.corpus = str(corpus)
    args.candidate_dir = tmp_path / "experimental-runtime"
    (args.candidate_dir / "src/omnichunk").mkdir(parents=True)
    (args.candidate_dir / "src/omnichunk/__init__.py").write_text("")
    args.tools = "omnichunk-pack,langchain-code,llamaindex-sentence,chonkie-sentence"
    calls = []

    def command(arguments, environment, output):
        calls.append((arguments, environment))
        output.write_text("captured stdout")
        Path(arguments[arguments.index("--output") + 1]).write_text("{}")

    monkeypatch.setattr(experiment, "_command", command)
    manifest = experiment.run(args)
    assert manifest["corpus_path"] == str(corpus)
    assert manifest["candidate_source"] == str(args.candidate_dir)
    assert manifest["tools"] == args.tools.split(",")
    assert manifest["comparison_anchor_tool"] == "omnichunk-pack"
    preparations = [item for item in calls if item[0][0] == "benchmarks/prepare_dense.py"]
    assert [env["PYTHONPATH"] for _, env in preparations] == [
        str(args.baseline_dir / "src"),
        str(args.candidate_dir / "src"),
    ]
    for arguments, _ in calls[:4]:
        assert arguments[arguments.index("--corpus") + 1] == str(corpus)
        assert arguments[arguments.index("--tools") + 1] == args.tools
    comparisons = [
        arguments for arguments, _ in calls if arguments[0].endswith("compare_retrieval.py")
    ]
    assert len(comparisons) == 4
    assert all(
        arguments[arguments.index("--baseline-tool") + 1] == "omnichunk-pack"
        for arguments in comparisons
    )


@pytest.mark.parametrize("tools", ["unknown", "omnichunk,unknown", "", "omnichunk,omnichunk"])
def test_unknown_empty_or_duplicate_strategy_is_rejected_before_inference(
    tmp_path, monkeypatch, tools
):
    args = configuration(tmp_path)
    args.tools = tools
    monkeypatch.setattr(experiment, "_command", lambda *args: pytest.fail("must not encode"))
    with pytest.raises(ValueError, match="--tools"):
        experiment.run(args)
    assert not args.output_dir.exists()


def test_cli_accepts_external_path_candidate_and_new_strategy(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(experiment, "run", lambda args: captured.append(args) or {})
    assert (
        experiment.main(
            [
                "--model-dir",
                str(tmp_path / "model"),
                "--model-revision",
                "a" * 40,
                "--baseline-dir",
                str(tmp_path / "baseline"),
                "--candidate-dir",
                str(tmp_path / "candidate"),
                "--corpus",
                str(tmp_path / "external"),
                "--tools",
                "langchain-code",
                "--output-dir",
                str(tmp_path / "results"),
            ]
        )
        == 0
    )
    assert captured[0].candidate_dir == tmp_path / "candidate"
    assert captured[0].corpus == str(tmp_path / "external")
    assert captured[0].tools == "langchain-code"


def test_missing_local_snapshot_is_an_actionable_cli_error(tmp_path, capsys):
    assert (
        experiment.main(
            [
                "--model-dir",
                str(tmp_path / "missing"),
                "--model-revision",
                "a" * 40,
                "--baseline-dir",
                str(tmp_path),
                "--corpus",
                "corpus_v1",
                "--output-dir",
                str(tmp_path / "results"),
            ]
        )
        == 2
    )
    assert "existing local snapshot" in capsys.readouterr().err

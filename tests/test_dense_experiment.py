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

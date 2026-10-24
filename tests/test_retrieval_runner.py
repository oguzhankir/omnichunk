from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import omnichunk
from benchmarks import run_retrieval as runner
from benchmarks.retrieval.adapters import AdapterUnavailable, Passage
from benchmarks.retrieval.ranking import LexicalRetriever, select_budget


def _passage(identifier: str, text: str) -> Passage:
    return Passage(identifier, identifier, 0, len(text.encode()), text)


def _fixture_corpus(root: Path) -> Path:
    records = []
    queries = []
    for name, text, language, split, question in (
        (
            "retention",
            "Customer backups expire after thirty days.\n",
            "en",
            "dev",
            "backups expire",
        ),
        ("erisim", "Erişim anahtarı her otuz günde yenilenir.\n", "tr", "dev", "Erişim anahtarı"),
        ("saklama", "監査記録は九十日保存します。\n", "ja", "test", "監査記録の保存"),
    ):
        filename = f"{name}.txt"
        raw = text.encode()
        (root / filename).write_bytes(raw)
        records.append(
            {
                "source_id": name,
                "path": filename,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "language": language,
                "category": "markdown",
                "split": split,
            }
        )
        queries.append(
            {
                "query_id": name,
                "text": question,
                "split": split,
                "evidence": [{"source_id": name, "start": 0, "end": len(raw), "quote": text}],
            }
        )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": "tiny-v1",
                "license": "MIT",
                "documents": records,
                "queries": queries,
            }
        ),
        encoding="utf-8",
    )
    return root


@pytest.mark.parametrize("query,expected", [("Erişim anahtarı", "tr"), ("監査記録の保存", "ja")])
def test_lexical_control_retrieves_multilingual_evidence(query: str, expected: str) -> None:
    passages = [
        _passage("tr", "Erişim anahtarı yenilenir."),
        _passage("ja", "監査記録を保存します。"),
    ]
    retriever = LexicalRetriever([p.text for p in passages])
    assert retriever.index(passages).rank(query)[0][0].passage_id == expected
    assert retriever.index(passages).rank("🦕🦕") == []


def test_document_idf_is_unchanged_by_chunking_and_ties_are_stable() -> None:
    retriever = LexicalRetriever(["alpha beta", "gamma delta"])
    expected = dict(retriever.idf)
    passages = [_passage("b", "alpha"), _passage("a", "alpha")]
    assert [p.passage_id for p, _ in retriever.index(passages).rank("alpha")] == ["a", "b"]
    retriever.index([_passage("c", "gamma")]).rank("beta")
    assert retriever.idf == expected
    with pytest.raises(ValueError, match="source document"):
        LexicalRetriever([])


def test_budget_counts_complete_payload_and_stops_at_first_overflow() -> None:
    ranked = [(_passage("a", "aa"), 1.0), (_passage("b", "bbbb"), 0.5), (_passage("c", "c"), 0.1)]
    assert select_budget(ranked, 7, len) == ranked[:1]
    assert select_budget(ranked, 8, len) == ranked[:2]

    # Tokenization may merge across boundaries; sum(per-passage) is not a valid counter.
    def count(text: str) -> int:
        return 1 if text == "aa\n\nbbbb" else len(text)

    assert select_budget(ranked, 2, count) == ranked[:2]
    with pytest.raises(ValueError, match="positive integer"):
        select_budget(ranked, 0, len)


def test_report_preserves_splits_diagnostics_and_evidence(tmp_path: Path) -> None:
    corpus = _fixture_corpus(tmp_path)
    output = tmp_path / "report.json"
    command = [
        "--corpus",
        str(corpus),
        "--tools",
        "omnichunk,fixed",
        "--chunk-sizes",
        "20",
        "--repeats",
        "1",
        "--retrieval-budget",
        "60",
        "--output",
        str(output),
    ]
    assert runner.main(command) == 0
    report = json.loads(output.read_text())
    assert report["queries"] == report["documents"] == 2
    assert report["configuration"]["split"] == "dev"
    for candidate in report["candidates"]:
        assert candidate["status"] == "ok"
        assert candidate["max_payload_size"] <= 20
        assert len(candidate["chunk_seconds_samples"]) == 1
        assert {row["query_id"] for row in candidate["per_query"]} == {"retention", "erisim"}
        assert all(row["budget_used"] <= 60 for row in candidate["per_query"])
    # No test document enters tuning or IDF fitting. Test requires explicit selection.
    assert runner.main([*command, "--split", "test"]) == 0
    assert json.loads(output.read_text())["queries"] == 1


@pytest.mark.parametrize(
    "error,status,exit_code",
    [
        (AdapterUnavailable("missing optional API"), "unavailable", 0),
        (ValueError("budget violated"), "error", 1),
    ],
)
def test_candidate_failure_is_visible_and_never_aggregated(
    tmp_path: Path, monkeypatch, error: Exception, status: str, exit_code: int
) -> None:
    corpus = _fixture_corpus(tmp_path)
    output = tmp_path / "report.json"

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(runner, "split_document", fail)
    command = [
        "--corpus",
        str(corpus),
        "--tools",
        "fixed",
        "--chunk-sizes",
        "20",
        "--output",
        str(output),
    ]
    assert runner.main(command) == exit_code
    candidate = json.loads(output.read_text())["candidates"][0]
    assert candidate["status"] == status and "summary" not in candidate
    assert runner.main([*command, "--require-all"]) == 1


def test_nondeterministic_adapter_fails_instead_of_mixing_qrels(
    tmp_path: Path, monkeypatch
) -> None:
    corpus = _fixture_corpus(tmp_path)
    count = 0
    real_split = runner.split_document

    def nondeterministic(*args, **kwargs):
        nonlocal count
        count += 1
        passages = real_split(*args, **kwargs)
        return passages if count <= 2 else passages[1:]

    monkeypatch.setattr(runner, "split_document", nondeterministic)
    output = tmp_path / "report.json"
    assert (
        runner.main(
            [
                "--corpus",
                str(corpus),
                "--tools",
                "fixed",
                "--chunk-sizes",
                "20",
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert (
        "changed between repeated runs" in json.loads(output.read_text())["candidates"][0]["detail"]
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--chunk-sizes", "0"],
        ["--top-k", "0"],
        ["--tools", "not-a-tool"],
        ["--unit", "tokens", "--tokenizer", "approximate"],
    ],
)
def test_invalid_experiments_fail_before_evaluation(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as failure:
        runner.main(arguments)
    assert failure.value.code == 2


def test_missing_corpus_returns_actionable_error(tmp_path: Path, capsys) -> None:
    assert runner.main(["--corpus", str(tmp_path / "missing")]) == 2
    assert "Retrieval evaluation failed" in capsys.readouterr().err


def test_provenance_hashes_the_runtime_package() -> None:
    environment = runner._environment()
    root = Path(omnichunk.__file__).resolve().parent
    expected = hashlib.sha256(
        b"".join(
            path.relative_to(root).as_posix().encode() + path.read_bytes()
            for path in sorted(root.rglob("*.py"))
        )
    ).hexdigest()
    assert environment["source_sha256"] == expected
    assert environment["runtime_package_root"] == str(root)

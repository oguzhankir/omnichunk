from __future__ import annotations
import argparse, collections, hashlib, json, pathlib, unicodedata

parser = argparse.ArgumentParser(
    description="Rebuild pinned Belebele Turkish passage corpus without scoring"
)
parser.add_argument(
    "--repo-root",
    type=pathlib.Path,
    required=True,
    help="OmniChunk checkout containing pinned previous corpus manifests",
)
parser.add_argument(
    "--upstream-dir",
    type=pathlib.Path,
    default=pathlib.Path(__file__).resolve().parent / "upstream",
)
parser.add_argument("--output-dir", type=pathlib.Path, required=True)
parser.add_argument(
    "--include-validation", action="store_true", help="Only use after source/model/settings freeze"
)
a = parser.parse_args()
P = a.output_dir.resolve()
P.mkdir(parents=True, exist_ok=True)
U = a.upstream_dir.resolve()
HERE = pathlib.Path(__file__).resolve().parent

H = lambda b: hashlib.sha256(b).hexdigest()
N = lambda t: " ".join(unicodedata.normalize("NFC", t).split())
J = lambda p: json.loads(p.read_text())
protocol_path = HERE.parent / "belebele_protocol.json"
protocol = J(protocol_path)
ns = protocol["namespace"]
tr = [json.loads(z) for z in (U / "belebele-data-tur_Latn.jsonl").read_text().splitlines()]
en = [json.loads(z) for z in (U / "belebele-data-eng_Latn.jsonl").read_text().splitlines()]
oldtext = []
oldquery = set()
oldmanifest = []
for expected in J(HERE / "previous-manifests.json"):
    f = a.repo_root / expected["path"]
    assert H(f.read_bytes()) == expected["sha256"], f
    j = J(f)
    oldmanifest.append({"path": str(f.relative_to(a.repo_root)), "sha256": H(f.read_bytes())})
    oldtext.extend(N((f.parent / d["path"]).read_text()) for d in j["documents"])
    oldquery.update(N(q["text"]).casefold() for q in j["queries"])
eng = {(r["link"], r["question_number"]): r for r in en}
groups = collections.defaultdict(list)
for row in tr:
    groups[row["link"]].append(row)
eligible = []
excluded = []
for link, rows in groups.items():
    assert len(set(N(r["flores_passage"]) for r in rows)) == 1
    if len(rows) < 2:
        continue
    e = eng[(link, rows[0]["question_number"])]
    vals = [N(rows[0]["flores_passage"]), N(e["flores_passage"])]
    if any(v in old or old in v for v in vals for old in oldtext if len(old) > 40):
        excluded.append(link)
        continue
    if any(
        N(r["question"]).casefold() in oldquery
        or N(eng[(link, r["question_number"])]["question"]).casefold() in oldquery
        for r in rows
    ):
        excluded.append(link)
        continue
    eligible.append((link, rows))
eligible.sort(key=lambda p: (H((ns + p[0]).encode()), p[0]))
selected = eligible[: min(120, len(eligible) // 2 * 2)]
base = {
    "schema_version": 1,
    "corpus_id": "belebele-turkish-passage-v1",
    "license": "CC-BY-SA-4.0",
    "source": "https://huggingface.co/datasets/facebook/belebele",
    "provenance": {
        "dataset_revision": protocol["revision"],
        "authors": "Belebele authors: Bandarkar et al., 2023; FLORES source contributors",
        "upstream_sha256": H((U / "belebele-data-tur_Latn.jsonl").read_bytes()),
        "paired_english_sha256": H((U / "belebele-data-eng_Latn.jsonl").read_bytes()),
        "protocol_sha256": H(protocol_path.read_bytes()),
        "evidence_policy": protocol["evidence_policy"],
        "limitations": protocol["limitations"],
        "previous_manifests": oldmanifest,
        "selection_namespace": ns,
        "source_link_grouping": "Each upstream link has exactly one unique passage; link disjointness is enforced.",
    },
    "documents": [],
    "queries": [],
}
part = {s: json.loads(json.dumps(base)) for s in ["dev", "test"]}
seenq = {}
seenp = {}
for i, (link, rows) in enumerate(selected):
    s = "dev" if i % 2 == 0 else "test"
    if s == "test" and not a.include_validation:
        continue
    dest = P / ("development" if s == "dev" else "validation")
    (dest / "documents").mkdir(parents=True, exist_ok=True)
    rows.sort(
        key=lambda r: (H((ns + link + str(r["question_number"])).encode()), r["question_number"])
    )
    raw = rows[0]["flores_passage"].encode()
    sid = "belebele-tr-" + H(link.encode())[:20]
    fn = "documents/" + sid + ".txt"
    (dest / fn).write_bytes(raw)
    assert N(raw.decode()) not in seenp or seenp[N(raw.decode())] == s
    seenp[N(raw.decode())] = s
    part[s]["documents"].append(
        {
            "source_id": sid,
            "path": fn,
            "sha256": H(raw),
            "language": "tr",
            "category": "prose",
            "split": s,
            "upstream_link": link,
            "attribution": "Belebele authors and original FLORES source contributors: " + link,
        }
    )
    for row in rows[:2]:
        qnorm = N(row["question"]).casefold()
        assert qnorm not in seenq or seenq[qnorm] == s
        seenq[qnorm] = s
        part[s]["queries"].append(
            {
                "query_id": sid + "-q" + str(row["question_number"]),
                "text": row["question"],
                "split": s,
                "evidence": [
                    {"source_id": sid, "start": 0, "end": len(raw), "quote": raw.decode()}
                ],
                "upstream_question_number": row["question_number"],
                "upstream_link": link,
                "original_task": "multiple-choice reading comprehension adapted to passage retrieval",
            }
        )
for s in part:
    if s == "test" and not a.include_validation:
        continue
    dest = P / ("development" if s == "dev" else "validation")
    (dest / "manifest.json").write_text(json.dumps(part[s], ensure_ascii=False, indent=2) + "\n")
    (dest / "NOTICE.md").write_text(
        "Belebele Turkish subset, CC-BY-SA 4.0. Bandarkar et al. (2023), The Belebele Benchmark: a Parallel Reading Comprehension Dataset in 122 Language Variants. Original source links and contributors are attributed per document. https://huggingface.co/datasets/facebook/belebele\n"
    )
    (dest / "LICENSE").write_text(
        "CC-BY-SA-4.0\nhttps://creativecommons.org/licenses/by-sa/4.0/legalcode\n"
    )
    # Exact-byte and manifest conformance checks.
    import sys

    sys.path.insert(0, str(a.repo_root))
    sys.path.insert(0, str(a.repo_root / "src"))
    from benchmarks.retrieval.corpus import load_corpus

    c = load_corpus(dest)
    assert len(c.documents) == 60 and len(c.queries) == 120
expected = J(HERE / "commitment.json")
for name, key in [
    ("development", "development_manifest_sha256"),
    ("validation", "validation_manifest_sha256"),
]:
    if name == "validation" and not a.include_validation:
        continue
    actual = H((P / name / "manifest.json").read_bytes())
    assert actual == expected[key], (name, actual, expected[key])
    print(name, actual)

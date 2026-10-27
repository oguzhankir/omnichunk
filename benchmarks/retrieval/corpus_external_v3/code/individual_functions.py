"""Convert deterministic selected functions to one function per source document."""

from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parent


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


summary = {}
for name in ["development", "private-validation"]:
    folder = ROOT / name
    if not (folder / "manifest.json").exists():
        continue
    m = json.loads((folder / "manifest.json").read_text())
    old = m["documents"]
    queries = m["queries"]
    docs = []
    for d in old:
        text = (folder / d["path"]).read_bytes()
        oldsource = d["source_id"]
        for f in d["functions"]:
            q = next(
                q
                for q in queries
                if q["evidence"][0]["source_id"] == oldsource
                and q["evidence"][0]["start"] == f["start"]
            )
            code = text[f["start"] : f["end"]]
            assert code.decode() == q["evidence"][0]["quote"]
            source = "csn-f-" + sha(f["url"])[:24]
            path = "documents/" + source + ".py"
            (folder / path).write_bytes(code)
            doc = {
                **{
                    k: v
                    for k, v in d.items()
                    if k not in ["source_id", "path", "sha256", "functions", "transformation"]
                },
                "source_id": source,
                "path": path,
                "sha256": sha(code),
                "function": {**f, "start": 0, "end": len(code)},
                "transformation": "Single original extracted function;ASTdocstrings removed;nojoins",
            }
            lic = next(
                z for z in m["provenance"]["license_records"] if z["repository"] == d["repository"]
            )
            assert "/blob/" + lic["revision"] + "/" in f["url"]
            q["evidence"][0].update(source_id=source, start=0, end=len(code))
            docs.append(doc)
        (folder / d["path"]).unlink()
    m["documents"] = docs
    m["provenance"]["source_components"] = (
        "Each source is one transformed function;repository is independent bootstrap cluster"
    )
    for q in queries:
        full = q["text"]
        q["original_documentation_sha256"] = sha(full.encode())
        q["text"] = full.split(chr(10) + chr(10))[0].strip()
    m["provenance"]["query_policy"] = (
        "Original human documentation firstparagraph;no query text generation;not fullparameter documentation"
    )
    m["provenance"]["protocol_sha256"] = sha((ROOT / "protocol.json").read_bytes())
    m["provenance"]["source_components"] = (
        "Each source is one transformed function;repository is independent bootstrap cluster"
    )
    (folder / "manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n")
    summary["dev" if name == "development" else "test"] = {
        "documents": len(docs),
        "queries": len(queries),
        "repository_clusters": len({d["repository"] for d in docs}),
        "manifest_sha256": sha((folder / "manifest.json").read_bytes()),
        "source_bytes": sum(len((folder / d["path"]).read_bytes()) for d in docs),
    }
(ROOT / "build-summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary))

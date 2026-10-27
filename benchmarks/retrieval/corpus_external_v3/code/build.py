from pathlib import Path
import argparse, ast, collections, concurrent.futures, hashlib, json, re, textwrap, urllib.request
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent
UP = ROOT / "upstream"
NS = "omnichunk-codesearchnet-v3-2026-10-27"


def sha(x):
    return hashlib.sha256(x if isinstance(x, bytes) else x.encode()).hexdigest()


def norm(x):
    return " ".join(x.split()).casefold()


def transformed(s):
    s = textwrap.dedent(s)
    t = ast.parse(s)
    if len(t.body) != 1 or not isinstance(t.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    fn = t.body[0]
    if (
        not fn.body
        or not isinstance(fn.body[0], ast.Expr)
        or not isinstance(fn.body[0].value, ast.Constant)
        or not isinstance(fn.body[0].value.value, str)
    ):
        return None
    b = s.encode()
    lines = s.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line.encode()))
    ranges = []
    for n in ast.walk(t):
        body = getattr(n, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            z = body[0]
            ranges.append(
                (starts[z.lineno - 1] + z.col_offset, starts[z.end_lineno - 1] + z.end_col_offset)
            )
    for a, z in sorted(ranges, reverse=True):
        b = b[:a] + b[z:]
    s = b.decode().strip() + "\n"
    ast.parse(s)
    return s


def prep(rows):
    d = collections.defaultdict(list)
    seenq = set()
    seenc = set()
    for r in sorted(
        rows,
        key=lambda r: (
            sha(NS + "|" + r["func_code_url"] + "|" + r["func_name"]),
            r["func_code_url"],
        ),
    ):
        q = r["func_documentation_string"].strip()
        if not 10 <= len(q) <= 1000:
            continue
        try:
            c = transformed(r["func_code_string"])
        except (SyntaxError, ValueError, TypeError):
            continue
        if (
            c is None
            or not 80 <= len(c.encode()) <= 8000
            or norm(q) in norm(c)
            or norm(q) in seenq
            or norm(c) in seenc
        ):
            continue
        seenq.add(norm(q))
        seenc.add(norm(c))
        d[r["repository_name"]].append((r, q, c))
    return {repo: items for repo, items in d.items() if len(items) >= 4}


def license_for(repo, items):
    url = items[0][0]["func_code_url"]
    m = re.match(r"https://github.com/([^/]+/[^/]+)/blob/([^/]+)/", url)
    if not m:
        return None
    rev = m.group(2)
    for name in ["LICENSE", "LICENSE.txt", "LICENSE.md", "LICENCE", "COPYING"]:
        u = f"https://raw.githubusercontent.com/{repo}/{rev}/{name}"
        try:
            b = urllib.request.urlopen(u, timeout=12).read()
            s = b.decode("utf-8")
        except Exception:
            continue
        if "Permission is hereby granted, free of charge" in s and "THE SOFTWARE IS PROVIDED" in s:
            return {
                "repository": repo,
                "revision": rev,
                "url": u,
                "sha256": sha(b),
                "text": s,
                "spdx": "MIT",
            }
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild pinned CodeSearchNet function corpus")
    parser.add_argument(
        "--development-only",
        action="store_true",
        help="Do not reconstruct sealed validation data during development",
    )
    args = parser.parse_args()
    summary = {}
    parts = {}
    allrepos = []
    for part, split in (
        [("validation", "dev")]
        if args.development_only
        else [("validation", "dev"), ("test", "test")]
    ):
        rows = pq.read_table(UP / f"{part}-00000-of-00001.parquet").to_pylist()
        d = prep(rows)
        order = sorted(d, key=lambda x: sha(NS + "|" + x))
        selected = []
        attempts = []
        for start in range(0, len(order), 16):
            batch = order[start : start + 16]
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                rs = list(ex.map(lambda repo: license_for(repo, d[repo]), batch))
            attempts.extend(
                {"repository": repo, "mit_verified": lic is not None}
                for repo, lic in zip(batch, rs)
            )
            for repo, lic in zip(batch, rs):
                if lic is not None:
                    selected.append((repo, lic, d[repo][:4]))
            if len(selected) >= 16:
                break
        selected = selected[:16]
        parts[split] = selected
        allrepos.append(set(r for r, _, _ in selected))
        (ROOT / f"{split}-license-attempts.json").write_text(json.dumps(attempts, indent=2))
        print(part, "selected", len(selected), "eligible repos", len(order), flush=True)
    assert len(allrepos) < 2 or not allrepos[0] & allrepos[1]
    assert "test" not in parts or not (
        {norm(q) for _, _, items in parts["dev"] for _, q, _ in items}
        & {norm(q) for _, _, items in parts["test"] for _, q, _ in items}
    )
    for split, selected in parts.items():
        folder = ROOT / ("development" if split == "dev" else "private-validation")
        (folder / "documents").mkdir(parents=True, exist_ok=True)
        (folder / "licenses").mkdir(exist_ok=True)
        docs = []
        queries = []
        licenses = []
        for repo, lic, items in selected:
            source = "csn-" + sha(NS + "|" + repo)[:20]
            text = ""
            ranges = []
            for r, q, c in items:
                if text:
                    text += "\n\n"
                start = len(text.encode())
                text += c
                end = len(text.encode())
                ranges.append((r, q, c, start, end))
            path = "documents/" + source + ".py"
            (folder / path).write_text(text)
            lp = "licenses/" + source + ".txt"
            (folder / lp).write_text(lic["text"])
            lic = {k: v for k, v in lic.items() if k != "text"}
            lic["path"] = lp
            licenses.append(lic)
            docs.append(
                {
                    "source_id": source,
                    "path": path,
                    "sha256": sha(text),
                    "language": "en",
                    "category": "code",
                    "split": split,
                    "repository": repo,
                    "license": "MIT",
                    "attribution_license": lp,
                    "transformation": "ASTdocstrings removed;4extracted functions joined;not original file",
                    "functions": [
                        {
                            "url": r["func_code_url"],
                            "path": r["func_path_in_repository"],
                            "name": r["func_name"],
                            "start": a,
                            "end": z,
                        }
                        for r, q, c, a, z in ranges
                    ],
                }
            )
            for r, q, c, a, z in ranges:
                queries.append(
                    {
                        "query_id": "csn-q-" + sha(r["func_code_url"])[:24],
                        "text": q,
                        "split": split,
                        "evidence": [{"source_id": source, "start": a, "end": z, "quote": c}],
                    }
                )
        manifest = {
            "schema_version": 1,
            "corpus_id": "codesearchnet-python-mit-v3-" + split,
            "license": "MIT",
            "source": "https://github.com/github/CodeSearchNet",
            "provenance": {
                "dataset_revision": "bd0cf261e357a3eb5c8fba490d23ec1a1cd59555",
                "protocol_sha256": sha((ROOT / "protocol.json").read_bytes()),
                "dataset_partition": "validation" if split == "dev" else "test",
                "selection": "Predeclared deterministic hash selection;no scores",
                "query_authorship": "Original repository documentation/docstrings;not userquestions",
                "evidence_policy": "Whole transformed function;not dependency-complete evidence",
                "license_records": licenses,
            },
            "documents": docs,
            "queries": queries,
        }
        (folder / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        )
        summary[split] = {
            "documents": len(docs),
            "queries": len(queries),
            "manifest_sha256": sha((folder / "manifest.json").read_bytes()),
            "source_bytes": sum(len((folder / d["path"]).read_bytes()) for d in docs),
        }
    (ROOT / "build-summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    # Canonical publication layout: separate original functions, never bundles.
    exec(
        compile(
            (ROOT / "individual_functions.py").read_text(),
            str(ROOT / "individual_functions.py"),
            "exec",
        ),
        {"__name__": "__main__", "__file__": str(ROOT / "individual_functions.py")},
    )

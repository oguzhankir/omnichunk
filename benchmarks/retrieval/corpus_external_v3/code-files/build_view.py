"""Build a correlated real-file view of the fixed CodeSearchNet function corpus."""

from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import urllib.parse
import urllib.request


def sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def source_url(function_url: str) -> tuple[str, int, int]:
    m = re.fullmatch(
        r"https://github.com/([^/]+/[^/]+)/blob/([0-9a-f]{40})/(.+)#L(\d+)-L(\d+)", function_url
    )
    if not m:
        raise ValueError("Noncanonical exact-commit source URL or missing line range")
    repo, revision, filepath, begin, end = m.groups()
    return f"https://raw.githubusercontent.com/{repo}/{revision}/{filepath}", int(begin), int(end)


def transform(raw: bytes) -> tuple[bytes, ast.Module, list[int], list[tuple[int, int, bytes]]]:
    text = raw.decode("utf-8")
    if len(text) > 30000:
        raise ValueError("Original source exceeds 30000 Unicode characters")
    tree = ast.parse(text)
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line.encode("utf-8")))
    edits = []
    for owner in ast.walk(tree):
        if not isinstance(owner, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(owner, "body", None)
        if (
            isinstance(body, list)
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node = body[0]
            a = starts[node.lineno - 1] + node.col_offset
            b = starts[node.end_lineno - 1] + node.end_col_offset
            edits.append((a, b, b"pass" if len(body) == 1 else b""))
    edits.sort()
    for previous, current in zip(edits, edits[1:]):
        if previous[1] > current[0]:
            raise ValueError("Overlapping docstring edits")
    result = raw
    for a, b, replacement in reversed(edits):
        result = result[:a] + replacement + result[b:]
    parsed = ast.parse(result.decode())
    for node in ast.walk(parsed):
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and ast.get_docstring(node) is not None
        ):
            raise ValueError("Docstring remained after canonical transformation")
    return result, tree, starts, edits


def rebase(position: int, edits: list[tuple[int, int, bytes]]) -> int:
    delta = 0
    for a, b, replacement in edits:
        if a < position < b:
            raise ValueError("Requested source endpoint falls inside a removed docstring")
        if b <= position:
            delta += len(replacement) - (b - a)
    return position + delta


def function_span(
    document: dict, tree: ast.Module, starts: list[int], edits: list[tuple[int, int, bytes]]
) -> tuple[int, int, dict]:
    reference = document["function"]
    _, anchor_begin, anchor_end = source_url(reference["url"])
    expected_name = reference["name"].split(".")[-1]
    matches = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            or node.name != expected_name
        ):
            continue
        begin = min([node.lineno] + [d.lineno for d in node.decorator_list])
        if anchor_begin not in (begin, node.lineno) or node.end_lineno > anchor_end:
            continue
        matches.append((node, begin))
    if len(matches) != 1:
        raise ValueError(f"Expected one exact anchor/name AST function; found {len(matches)}")
    node, begin = matches[0]
    a = starts[begin - 1]
    b = starts[node.end_lineno]
    return (
        rebase(a, edits),
        rebase(b, edits),
        {
            "definition_line": node.lineno,
            "first_decorator_or_definition_line": begin,
            "last_body_line": node.end_lineno,
            "original_start": a,
            "original_end": b,
            "upstream_url": reference["url"],
            "name": reference["name"],
        },
    )


def build_view(manifest: dict, input_root: Path, output_root: Path, source_cache: Path) -> dict:
    here = Path(__file__).resolve().parent
    protocol_raw = (here / "protocol.json").read_bytes()
    source_cache.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "documents").mkdir(exist_ok=True)
    by_id = {d["source_id"]: d for d in manifest["documents"]}
    files = {}
    failures = []
    query_matches = []
    docs = {}
    queries = []
    retained_repositories = set()
    for query in manifest["queries"]:
        old = by_id[query["evidence"][0]["source_id"]]
        try:
            url, _, _ = source_url(old["function"]["url"])
            if url not in files:
                key = sha(url)
                cached = list(source_cache.glob(key + "*"))
                path = cached[0] if cached else source_cache / (key + ".py")
                raw = (
                    path.read_bytes()
                    if path.exists()
                    else urllib.request.urlopen(url, timeout=30).read()
                )
                path.write_bytes(raw)
                try:
                    canonical, tree, starts, edits = transform(raw)
                    files[url] = {
                        "raw": raw,
                        "canonical": canonical,
                        "tree": tree,
                        "starts": starts,
                        "edits": edits,
                    }
                except Exception as exc:
                    files[url] = {
                        "error": str(exc),
                        "raw_sha256": sha(raw),
                        "raw_bytes": len(raw),
                        "raw_characters": len(raw.decode("utf-8", errors="replace")),
                    }
            item = files[url]
            if "error" in item:
                raise ValueError(item["error"])
            a, b, reference = function_span(old, item["tree"], item["starts"], item["edits"])
            text = item["canonical"].decode("utf-8")
            quote = item["canonical"][a:b].decode("utf-8")
            if not quote.strip():
                raise ValueError("Empty function evidence after canonical transformation")
            sid = "csn-file-" + sha(url)[:24]
            if sid not in docs:
                rel = "documents/" + sid + ".py"
                (output_root / rel).write_bytes(item["canonical"])
                license_rel = old["attribution_license"]
                (output_root / license_rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(input_root / license_rel, output_root / license_rel)
                docs[sid] = {
                    "source_id": sid,
                    "path": rel,
                    "sha256": sha(item["canonical"]),
                    "language": "en",
                    "category": "code",
                    "split": old["split"],
                    "repository": old["repository"],
                    "license": "MIT",
                    "attribution_license": license_rel,
                    "upstream_raw_url": url,
                    "upstream_raw_sha256": sha(item["raw"]),
                    "upstream_raw_bytes": len(item["raw"]),
                    "upstream_characters": len(item["raw"].decode()),
                    "removed_ast_docstrings": len(item["edits"]),
                    "sole_body_pass_replacements": sum(bool(e[2]) for e in item["edits"]),
                    "function_references": [],
                    "transformation": "Complete original file;allASTdocstrings removed;solebodydocstrings replacedwithpass;nosyntheticjoins",
                }
            docs[sid]["function_references"].append(reference)
            exact = query["text"] in text
            folded = normalized(query["text"]) in normalized(text)
            if exact or folded:
                query_matches.append(
                    {
                        "query_id": query["query_id"],
                        "source_id": sid,
                        "exact_substring": exact,
                        "normalized_substring": folded,
                    }
                )
            queries.append(
                {
                    **{k: v for k, v in query.items() if k != "evidence"},
                    "evidence": [{"source_id": sid, "start": a, "end": b, "quote": quote}],
                    "original_function_source_id": old["source_id"],
                }
            )
            retained_repositories.add(old["repository"])
        except Exception as exc:
            failures.append(
                {
                    "query_id": query["query_id"],
                    "repository": old["repository"],
                    "upstream_function_url": old["function"]["url"],
                    "reason": type(exc).__name__ + ": " + str(exc),
                }
            )
    provenance = {
        **manifest["provenance"],
        "real_file_protocol_sha256": sha(protocol_raw),
        "isolated_function_manifest_sha256": sha((input_root / "manifest.json").read_bytes()),
        "task": "Correlated same-question real-original-file retrieval view;not independent",
        "gold_policy": "Whole selected ASTfunction with original indentation and complete lastline;rebased after docstring removal",
        "license_records": [
            x
            for x in manifest["provenance"]["license_records"]
            if x["repository"] in retained_repositories
        ],
        "source_components": "Original complete sourcefiles;repository is split and bootstrap cluster",
    }
    result = {
        "schema_version": 1,
        "corpus_id": manifest["corpus_id"] + "-real-files",
        "license": "MIT",
        "source": manifest["source"],
        "provenance": provenance,
        "documents": list(docs.values()),
        "queries": queries,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    clusters = {d["source_id"]: d["repository"] for d in docs.values()}
    (output_root / "repository-clusters.json").write_text(json.dumps(clusters, indent=2) + "\n")
    audit = {
        "input_function_documents": len(manifest["documents"]),
        "input_queries": len(manifest["queries"]),
        "input_repositories": len({d["repository"] for d in manifest["documents"]}),
        "queried_unique_original_files": len(files),
        "eligible_source_files": len(docs),
        "retained_queries": len(queries),
        "retained_repositories": len(retained_repositories),
        "excluded_queries": len(failures),
        "failures": failures,
        "query_substring_matches": query_matches,
        "manifest_sha256": sha((output_root / "manifest.json").read_bytes()),
        "raw_file_outcomes": [
            {
                "url": url,
                **{
                    k: v
                    for k, v in item.items()
                    if k in ["error", "raw_sha256", "raw_bytes", "raw_characters"]
                },
                **(
                    {
                        "raw_sha256": sha(item["raw"]),
                        "raw_bytes": len(item["raw"]),
                        "raw_characters": len(item["raw"].decode()),
                    }
                    if "raw" in item
                    else {}
                ),
            }
            for url, item in files.items()
        ],
        "selection_uses_retrieval_scores": False,
    }
    (output_root / "build-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-cache", type=Path, required=True)
    args = parser.parse_args()
    m = json.loads(args.manifest.read_text())
    audit = build_view(m, args.manifest.parent, args.output_dir, args.source_cache)
    print(
        json.dumps(
            {
                k: v
                for k, v in audit.items()
                if k not in ["failures", "query_substring_matches", "raw_file_outcomes"]
            }
        )
    )

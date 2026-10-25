"""Import a checksum-pinned, article-disjoint SQuAD 1.1 retrieval corpus offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

SQUAD_URL = (
    "https://raw.githubusercontent.com/rajpurkar/SQuAD-explorer/master/dataset/dev-v1.1.json"
)
SQUAD_SHA256 = "95aa6a52d5d6a735563366753ca50492a658031da74f301ac5238b03966972c9"
LICENSE_NOTICE = """SQuAD 1.1 selected retrieval corpus — CC BY-SA 4.0

Dataset: Stanford Question Answering Dataset (SQuAD), by Pranav Rajpurkar,
Jian Zhang, Konstantin Lopyrev and Percy Liang.
https://rajpurkar.github.io/SQuAD-explorer/
Source paragraphs: Wikipedia contributors; per-article attribution links are
recorded in manifest.json. Questions and answer annotations are from SQuAD 1.1.
License: Creative Commons Attribution-ShareAlike 4.0 International
https://creativecommons.org/licenses/by-sa/4.0/

Changes: a deterministic subset was selected; document and query IDs, exact UTF-8
byte evidence ranges, checksums and article-disjoint evaluation splits were added.
The paragraph and question text is unmodified. This corpus is licensed separately
from the OmniChunk software. Redistributed adaptations must retain attribution
and comply with the linked ShareAlike license.
"""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _answer(context: str, question: dict[str, Any]) -> tuple[int, int, str]:
    for answer in question.get("answers", []):
        if not isinstance(answer, dict):
            continue
        start, text = answer.get("answer_start"), answer.get("text")
        if (
            type(start) is int
            and start >= 0
            and isinstance(text, str)
            and text.strip()
            and context[start : start + len(text)] == text
        ):
            byte_start = len(context[:start].encode("utf-8"))
            return byte_start, byte_start + len(text.encode("utf-8")), text
    raise ValueError(f"Question has no matching answer annotation: {question.get('id')!r}")


def _import_squad(
    source: Path,
    output: Path,
    *,
    expected_sha256: str = SQUAD_SHA256,
    articles: int = 16,
    paragraphs_per_article: int = 2,
    questions_per_paragraph: int = 3,
) -> dict[str, Any]:
    """Build a fixed-size subset; expected_sha256 is injectable for fixture tests."""
    if any(
        type(n) is not int or n < 1
        for n in (articles, paragraphs_per_article, questions_per_paragraph)
    ):
        raise ValueError("Selection counts must be positive integers")
    if articles < 2:
        raise ValueError("At least two articles are required for disjoint splits")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("SQuAD input checksum differs from the pinned dataset")
    dataset = json.loads(raw)
    if not isinstance(dataset, dict) or dataset.get("version") != "1.1":
        raise ValueError("Expected SQuAD dataset version 1.1")
    if not isinstance(dataset.get("data"), list):
        raise ValueError("SQuAD data must contain articles")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output must be a new or empty directory")

    documents: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    seen_contexts: set[str] = set()
    seen_questions: set[str] = set()
    seen_titles: set[str] = set()
    selected_articles: list[str] = []
    for article in sorted(dataset["data"], key=lambda item: (_hash(item["title"]), item["title"])):
        title = article["title"]
        if not isinstance(title, str) or not title.strip() or title in seen_titles:
            raise ValueError("Article titles must be unique nonempty strings")
        seen_titles.add(title)
        selected = []
        local_contexts: set[str] = set()
        local_questions: set[str] = set()
        for paragraph in sorted(article["paragraphs"], key=lambda item: _hash(item["context"])):
            context = paragraph["context"]
            normalized = _normalized(context)
            if not normalized or normalized in seen_contexts | local_contexts:
                continue
            chosen = []
            for question in sorted(
                paragraph["qas"], key=lambda item: (_hash(item["id"]), item["id"])
            ):
                text = question["question"]
                normalized_question = _normalized(text)
                if (
                    not normalized_question
                    or normalized_question in seen_questions | local_questions
                ):
                    continue
                start, end, answer = _answer(context, question)
                chosen.append((question, start, end, answer))
                local_questions.add(normalized_question)
                if len(chosen) == questions_per_paragraph:
                    break
            if len(chosen) == questions_per_paragraph:
                selected.append((context, chosen))
                local_contexts.add(normalized)
            else:
                # A rejected paragraph must not reserve questions from later ones.
                for question, *_ in chosen:
                    local_questions.discard(_normalized(question["question"]))
            if len(selected) == paragraphs_per_article:
                break
        if len(selected) != paragraphs_per_article:
            continue
        split = "dev" if len(selected_articles) % 2 == 0 else "test"
        selected_articles.append(title)
        seen_contexts.update(local_contexts)
        seen_questions.update(local_questions)
        article_url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="")
        for context, chosen in selected:
            source_id = "squad-" + _hash(title + "\n" + context)
            relative = f"documents/{source_id}.txt"
            texts[relative] = context
            documents.append(
                {
                    "source_id": source_id,
                    "path": relative,
                    "sha256": _hash(context),
                    "language": "en",
                    "category": "prose",
                    "split": split,
                    "article_title": title,
                    "source": article_url,
                    "attribution": f"Wikipedia contributors: {title}; SQuAD 1.1",
                }
            )
            for question, start, end, answer in chosen:
                queries.append(
                    {
                        "query_id": "squad-" + question["id"],
                        "text": question["question"],
                        "split": split,
                        "evidence": [
                            {"source_id": source_id, "start": start, "end": end, "quote": answer}
                        ],
                    }
                )
        if len(selected_articles) == articles:
            break
    if len(selected_articles) != articles:
        raise ValueError("Dataset has too few eligible unique articles for this selection")
    if len({query["query_id"] for query in queries}) != len(queries):
        raise ValueError("Selected SQuAD question IDs are not unique")
    manifest = {
        "schema_version": 1,
        "corpus_id": "squad-1.1-retrieval-v1",
        "license": "CC-BY-SA-4.0",
        "source": "https://rajpurkar.github.io/SQuAD-explorer/",
        "provenance": {
            "upstream_url": SQUAD_URL,
            "upstream_sha256": digest,
            "upstream_version": "1.1",
            "authors": ["Pranav Rajpurkar", "Jian Zhang", "Konstantin Lopyrev", "Percy Liang"],
            "paragraph_attribution": "Wikipedia contributors; per-document source links",
            "selection": (
                "SHA256 order of article titles, paragraph text and question IDs; "
                "no retrieval scores used"
            ),
            "articles": articles,
            "paragraphs_per_article": paragraphs_per_article,
            "questions_per_paragraph": questions_per_paragraph,
            "selected_articles": selected_articles,
            "split_policy": (
                "Alternating article assignment in selected hash order; dev/test article-disjoint"
            ),
            "answer_policy": (
                "First annotation whose exact text matches answer_start; "
                "one answer span per question"
            ),
            "limitations": (
                "Small English Wikipedia prose subset, not representative of code/tables or "
                "multilingual retrieval; no independent OmniChunk-specific human review"
            ),
        },
        "documents": documents,
        "queries": queries,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "documents").mkdir()
    for relative, text in texts.items():
        (output / relative).write_bytes(text.encode("utf-8"))
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "LICENSE").write_text(LICENSE_NOTICE, encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Previously downloaded dev-v1.1.json; checksum is pinned",
    )
    parser.add_argument("--output", type=Path, required=True, help="New or empty output directory")
    args = parser.parse_args(argv)
    try:
        manifest = _import_squad(args.input, args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"SQuAD import failed: {exc}\n")
    print(f"Imported {len(manifest['documents'])} documents and {len(manifest['queries'])} queries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

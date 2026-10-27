"""A frozen lexical control, independent of the chunking configuration.

IDF is fitted on source documents, never chunks or queries. Unicode character
2–4 grams allow the same offline control to operate on whitespace-free scripts.
This is a lexical baseline, not a multilingual semantic embedding model.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence

from .adapters import Passage

MODEL_REVISION = "lexical-char-2-4-tfidf-v1"


def _terms(text: str) -> Counter[str]:
    normalized = " ".join(text.casefold().split())
    return Counter(
        normalized[start : start + width]
        for width in (2, 3, 4)
        for start in range(len(normalized) - width + 1)
    )


class LexicalRetriever:
    """Fit source-document IDF once, then index each candidate's passages."""

    def __init__(self, documents: Sequence[str]) -> None:
        if not documents:
            raise ValueError("The retriever needs at least one source document")
        frequencies: Counter[str] = Counter()
        for text in documents:
            frequencies.update(_terms(text).keys())
        self.idf = {
            term: math.log((1 + len(documents)) / (1 + frequency)) + 1
            for term, frequency in frequencies.items()
        }

    def _vector(self, text: str) -> dict[str, float]:
        vector = {
            term: (1 + math.log(count)) * self.idf[term]
            for term, count in _terms(text).items()
            if term in self.idf
        }
        norm = math.sqrt(sum(value * value for value in vector.values()))
        return {term: value / norm for term, value in vector.items()} if norm else {}

    def index(self, passages: Sequence[Passage]) -> PassageIndex:
        return PassageIndex(self, passages)


class PassageIndex:
    def __init__(self, retriever: LexicalRetriever, passages: Sequence[Passage]) -> None:
        self.retriever = retriever
        self.passages = [(passage, retriever._vector(passage.text)) for passage in passages]

    def rank(self, query: str) -> list[tuple[Passage, float]]:
        vector = self.retriever._vector(query)
        ranked = []
        for passage, candidate in self.passages:
            score = sum(weight * candidate.get(term, 0) for term, weight in vector.items())
            if score > 0:
                ranked.append((passage, score))
        return sorted(ranked, key=lambda item: (-item[1], item[0].passage_id))


def select_budget(
    ranked: Sequence[tuple[Passage, float]], capacity: int, counter: Callable[[str], int]
) -> list[tuple[Passage, float]]:
    """Select a rank prefix whose entire rendered context fits the budget.

    Include two newline separators; do not assume token counts are additive.
    Stop at the first non-fitting passage, without skipping or truncating it.
    """
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise ValueError("Retrieval capacity must be a positive integer")
    selected: list[tuple[Passage, float]] = []
    texts: list[str] = []
    for passage, score in ranked:
        candidate = "\n\n".join([*texts, passage.text])
        if counter(candidate) > capacity:
            break
        selected.append((passage, score))
        texts.append(passage.text)
    return selected

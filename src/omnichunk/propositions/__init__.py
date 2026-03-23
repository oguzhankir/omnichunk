from omnichunk.propositions.heuristic import extract_propositions_heuristic
from omnichunk.propositions.llm_extract import extract_propositions_llm
from omnichunk.propositions.types import Proposition

__all__ = [
    "Proposition",
    "extract_propositions_heuristic",
    "extract_propositions_llm",
]

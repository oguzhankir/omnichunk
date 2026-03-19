from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ASTNodeWindowItem:
    node: Any | None
    start: int
    end: int
    size: int

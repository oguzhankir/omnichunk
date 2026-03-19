from __future__ import annotations

import re

from omnichunk.types import EntityInfo, EntityType, ImportInfo


def build_import_infos(entities: list[EntityInfo]) -> list[ImportInfo]:
    imports = [e for e in entities if e.type == EntityType.IMPORT]
    out: list[ImportInfo] = []

    for entity in imports:
        source = _extract_source(entity.signature)
        out.append(
            ImportInfo(
                name=entity.name,
                source=source,
                is_default=_looks_default_import(entity.signature),
                is_namespace=_looks_namespace_import(entity.signature),
            )
        )

    unique: list[ImportInfo] = []
    seen: set[tuple[str, str, bool, bool]] = set()
    for imp in out:
        key = (imp.name, imp.source, imp.is_default, imp.is_namespace)
        if key in seen:
            continue
        seen.add(key)
        unique.append(imp)

    return unique


def filter_imports_for_chunk(imports: list[ImportInfo], signatures: list[str]) -> list[ImportInfo]:
    if not signatures:
        return []

    haystack = "\n".join(signatures)
    filtered: list[ImportInfo] = []
    for imp in imports:
        pattern = rf"\b{re.escape(imp.name)}\b"
        if re.search(pattern, haystack):
            filtered.append(imp)

    if filtered:
        return filtered

    return imports[: min(6, len(imports))]


def _extract_source(signature: str) -> str:
    if not signature:
        return ""

    from_match = re.search(r"\bfrom\s+([A-Za-z0-9_\./\-]+)", signature)
    if from_match:
        return from_match.group(1)

    quote_match = re.search(r"['\"]([^'\"]+)['\"]", signature)
    if quote_match:
        return quote_match.group(1)

    return ""


def _looks_default_import(signature: str) -> bool:
    return bool(re.search(r"\bimport\s+[A-Za-z_$][\w$]*\s+from\b", signature))


def _looks_namespace_import(signature: str) -> bool:
    return "* as " in signature

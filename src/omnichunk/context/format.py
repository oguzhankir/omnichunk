from __future__ import annotations

from omnichunk.types import ChunkContext, EntityType


def format_contextualized_text(text: str, context: ChunkContext, overlap_text: str = "") -> str:
    parts: list[str] = []

    if context.filepath:
        rel_path = "/".join(context.filepath.replace("\\", "/").split("/")[-3:])
        parts.append(f"# {rel_path}")

    if context.language and context.language != "plaintext":
        parts.append(f"# Language: {context.language}")

    if context.heading_hierarchy:
        parts.append(f"# Section: {' > '.join(context.heading_hierarchy)}")

    if context.scope:
        scope_path = " > ".join(e.name for e in reversed(context.scope) if e.name)
        if scope_path:
            parts.append(f"# Scope: {scope_path}")

    signatures = [e.signature for e in context.entities if e.signature and e.type != EntityType.IMPORT]
    if signatures:
        parts.append(f"# Defines: {', '.join(signatures[:5])}")

    if context.imports:
        import_names = [i.name for i in context.imports[:10] if i.name]
        if import_names:
            parts.append(f"# Uses: {', '.join(import_names)}")

    before = [s.name for s in context.siblings if s.position == "before"]
    after = [s.name for s in context.siblings if s.position == "after"]
    if before:
        parts.append(f"# After: {', '.join(before)}")
    if after:
        parts.append(f"# Before: {', '.join(after)}")

    if context.parse_errors:
        parts.append(f"# ParseErrors: {'; '.join(context.parse_errors[:3])}")

    if parts:
        parts.append("")

    if overlap_text:
        parts.append("# ...")
        parts.append(overlap_text)
        parts.append("# ---")

    parts.append(text)
    return "\n".join(parts)

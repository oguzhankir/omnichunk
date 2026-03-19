from __future__ import annotations

from dataclasses import replace
import re
from typing import Any, Iterable

from omnichunk.parser.languages import get_language
from omnichunk.parser.query_patterns import get_query_source
from omnichunk.types import ByteRange, EntityInfo, EntityType, Language, LineRange

try:
    from tree_sitter import Query as TSQuery
    from tree_sitter import QueryCursor as TSQueryCursor
except Exception:
    TSQuery = None  # type: ignore[assignment]
    TSQueryCursor = None  # type: ignore[assignment]

ENTITY_NODE_TYPES: dict[Language, dict[str, EntityType]] = {
    "python": {
        "function_definition": EntityType.FUNCTION,
        "class_definition": EntityType.CLASS,
        "import_statement": EntityType.IMPORT,
        "import_from_statement": EntityType.IMPORT,
        "decorated_definition": EntityType.DECORATOR,
        "assignment": EntityType.CONSTANT,
    },
    "javascript": {
        "function_declaration": EntityType.FUNCTION,
        "method_definition": EntityType.METHOD,
        "class_declaration": EntityType.CLASS,
        "import_statement": EntityType.IMPORT,
        "export_statement": EntityType.EXPORT,
    },
    "typescript": {
        "function_declaration": EntityType.FUNCTION,
        "method_definition": EntityType.METHOD,
        "class_declaration": EntityType.CLASS,
        "interface_declaration": EntityType.INTERFACE,
        "type_alias_declaration": EntityType.TYPE,
        "enum_declaration": EntityType.ENUM,
        "import_statement": EntityType.IMPORT,
        "export_statement": EntityType.EXPORT,
    },
    "rust": {
        "function_item": EntityType.FUNCTION,
        "impl_item": EntityType.CLASS,
        "struct_item": EntityType.CLASS,
        "trait_item": EntityType.INTERFACE,
        "enum_item": EntityType.ENUM,
        "use_declaration": EntityType.IMPORT,
    },
    "go": {
        "function_declaration": EntityType.FUNCTION,
        "method_declaration": EntityType.METHOD,
        "type_declaration": EntityType.TYPE,
        "import_declaration": EntityType.IMPORT,
    },
    "java": {
        "method_declaration": EntityType.METHOD,
        "class_declaration": EntityType.CLASS,
        "interface_declaration": EntityType.INTERFACE,
        "enum_declaration": EntityType.ENUM,
        "import_declaration": EntityType.IMPORT,
    },
    "c": {
        "function_definition": EntityType.FUNCTION,
        "declaration": EntityType.CONSTANT,
        "preproc_include": EntityType.IMPORT,
    },
    "cpp": {
        "function_definition": EntityType.FUNCTION,
        "class_specifier": EntityType.CLASS,
        "struct_specifier": EntityType.CLASS,
        "preproc_include": EntityType.IMPORT,
    },
    "csharp": {
        "method_declaration": EntityType.METHOD,
        "class_declaration": EntityType.CLASS,
        "interface_declaration": EntityType.INTERFACE,
        "enum_declaration": EntityType.ENUM,
        "using_directive": EntityType.IMPORT,
    },
    "ruby": {
        "method": EntityType.METHOD,
        "class": EntityType.CLASS,
        "module": EntityType.MODULE,
        "call": EntityType.FUNCTION,
    },
    "php": {
        "function_definition": EntityType.FUNCTION,
        "method_declaration": EntityType.METHOD,
        "class_declaration": EntityType.CLASS,
        "interface_declaration": EntityType.INTERFACE,
        "trait_declaration": EntityType.TYPE,
        "namespace_use_declaration": EntityType.IMPORT,
    },
    "kotlin": {
        "function_declaration": EntityType.FUNCTION,
        "class_declaration": EntityType.CLASS,
        "object_declaration": EntityType.CLASS,
        "interface_declaration": EntityType.INTERFACE,
        "import_header": EntityType.IMPORT,
    },
    "swift": {
        "function_declaration": EntityType.FUNCTION,
        "class_declaration": EntityType.CLASS,
        "struct_declaration": EntityType.CLASS,
        "protocol_declaration": EntityType.INTERFACE,
        "import_declaration": EntityType.IMPORT,
    },
}

_QUERY_CAPTURE_ENTITY_TYPES: dict[str, EntityType] = {
    "entity.function": EntityType.FUNCTION,
    "entity.method": EntityType.METHOD,
    "entity.class": EntityType.CLASS,
    "entity.interface": EntityType.INTERFACE,
    "entity.type": EntityType.TYPE,
    "entity.enum": EntityType.ENUM,
    "entity.import": EntityType.IMPORT,
    "entity.export": EntityType.EXPORT,
    "entity.decorator": EntityType.DECORATOR,
}


def extract_entities(code: str, language: Language, tree: Any | None) -> list[EntityInfo]:
    """Extract entities with iterative AST traversal and graceful fallback."""
    if not code:
        return []

    if tree is None or getattr(tree, "root_node", None) is None:
        return _fallback_regex_entities(code, language)

    source_bytes = code.encode("utf-8")
    mapping = ENTITY_NODE_TYPES.get(language, {})
    entities: list[EntityInfo] = []

    query_matches = _collect_query_matches(language=language, tree=tree)
    if query_matches:
        matched_nodes: list[tuple[Any, EntityType]] = query_matches
    else:
        matched_nodes = []
        for node in _iter_ast_nodes(tree.root_node):
            node_type = getattr(node, "type", "")
            entity_type = mapping.get(node_type)
            if entity_type is None:
                continue
            matched_nodes.append((node, entity_type))

    for node, entity_type in matched_nodes:
        node_type = getattr(node, "type", "")

        effective_node = node
        name_node = node

        if language == "python" and node_type == "decorated_definition":
            target = _find_decorated_target(node)
            if target is not None:
                name_node = target
                target_type = mapping.get(getattr(target, "type", ""))
                if target_type is not None and target_type != EntityType.DECORATOR:
                    entity_type = target_type

        if entity_type == EntityType.IMPORT:
            entities.extend(_extract_import_entities(effective_node, source_bytes, language))
            continue

        name = _extract_entity_name(name_node, source_bytes, language)
        if not name:
            continue

        byte_range = _node_byte_range(effective_node)
        line_range = _node_line_range(effective_node)
        signature = _extract_signature(name_node, source_bytes, language)
        docstring = _extract_docstring(effective_node, source_bytes, language)
        parent = _find_parent_name(effective_node, source_bytes, language)

        entities.append(
            EntityInfo(
                name=name,
                type=entity_type,
                signature=signature,
                docstring=docstring,
                byte_range=byte_range,
                line_range=line_range,
                parent=parent,
            )
        )

    entities = _dedupe_entities(entities)
    entities.sort(key=lambda e: ((e.byte_range.start if e.byte_range else 0), e.name))

    return entities


def _iter_ast_nodes(root: Any) -> Iterable[Any]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        children = list(getattr(node, "children", []) or [])
        for child in reversed(children):
            stack.append(child)


def _collect_query_matches(language: Language, tree: Any | None) -> list[tuple[Any, EntityType]]:
    if tree is None:
        return []

    root = getattr(tree, "root_node", None)
    if root is None:
        return []

    query_source = get_query_source(language)
    if not query_source:
        return []

    lang_obj = get_language(language)
    if lang_obj is None:
        return []

    query = _compile_query(lang_obj, query_source)
    if query is None:
        return []

    captures = _run_query_captures(query, root)
    if not captures:
        return []

    out: list[tuple[Any, EntityType]] = []
    seen: set[tuple[str, int, int]] = set()
    for node, capture_name in captures:
        entity_type = _QUERY_CAPTURE_ENTITY_TYPES.get(capture_name)
        if entity_type is None:
            continue

        start = int(getattr(node, "start_byte", 0))
        end = int(getattr(node, "end_byte", start))
        key = (capture_name, start, end)
        if key in seen:
            continue
        seen.add(key)
        out.append((node, entity_type))

    return out


def _compile_query(language_obj: Any, query_source: str) -> Any | None:
    if TSQuery is not None:
        try:
            return TSQuery(language_obj, query_source)
        except Exception:
            pass

    query_method = getattr(language_obj, "query", None)
    if callable(query_method):
        try:
            return query_method(query_source)
        except Exception:
            pass

    return None


def _run_query_captures(query: Any, root: Any) -> list[tuple[Any, str]]:
    captures_method = getattr(query, "captures", None)
    if callable(captures_method):
        try:
            raw = captures_method(root)
            captures = _normalize_query_captures(raw, query)
            if captures:
                return captures
        except Exception:
            pass

    if TSQueryCursor is None:
        return []

    try:
        cursor = TSQueryCursor()
    except Exception:
        return []

    captures_method = getattr(cursor, "captures", None)
    if callable(captures_method):
        try:
            raw = captures_method(query, root)
            return _normalize_query_captures(raw, query)
        except Exception:
            return []

    return []


def _normalize_query_captures(raw: Any, query: Any) -> list[tuple[Any, str]]:
    out: list[tuple[Any, str]] = []

    if isinstance(raw, dict):
        for capture_name, nodes in raw.items():
            if not isinstance(nodes, (list, tuple)):
                continue
            for node in nodes:
                out.append((node, str(capture_name)))
        return out

    capture_names = list(getattr(query, "capture_names", []) or [])
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            node, capture = item

            if isinstance(capture, str):
                out.append((node, capture))
                continue

            if isinstance(capture, int) and 0 <= capture < len(capture_names):
                out.append((node, str(capture_names[capture])))

    return out


def _node_byte_range(node: Any) -> ByteRange:
    start = int(getattr(node, "start_byte", 0))
    end = int(getattr(node, "end_byte", start))
    if end < start:
        end = start
    return ByteRange(start=start, end=end)


def _node_line_range(node: Any) -> LineRange:
    start_point = getattr(node, "start_point", (0, 0))
    end_point = getattr(node, "end_point", start_point)
    start_row = int(start_point[0])
    end_row = int(end_point[0])
    if end_row < start_row:
        end_row = start_row
    return LineRange(start=start_row, end=end_row)


def _node_text(node: Any, source_bytes: bytes) -> str:
    start = int(getattr(node, "start_byte", 0))
    end = int(getattr(node, "end_byte", start))
    if end <= start:
        return ""
    return source_bytes[start:end].decode("utf-8", errors="replace")


def _find_decorated_target(node: Any) -> Any | None:
    for child in getattr(node, "children", []) or []:
        ctype = getattr(child, "type", "")
        if ctype in {"function_definition", "class_definition"}:
            return child
    return None


def _extract_entity_name(node: Any, source_bytes: bytes, language: Language) -> str:
    for field_name in ("name", "declarator", "type", "field"):
        child = _child_by_field_name(node, field_name)
        if child is not None:
            text = _node_text(child, source_bytes).strip()
            if text:
                return _normalize_name(text)

    snippet = _node_text(node, source_bytes)
    if not snippet:
        return ""

    regex_by_lang = {
        "python": r"\b(?:def|class)\s+([A-Za-z_][\w]*)",
        "javascript": r"\b(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
        "typescript": r"\b(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
        "rust": r"\b(?:fn|struct|enum|trait|impl)\s+([A-Za-z_][\w]*)",
        "go": r"\b(?:func|type)\s+([A-Za-z_][\w]*)",
        "java": r"\b(?:class|interface|enum)\s+([A-Za-z_][\w]*)",
        "kotlin": r"\b(?:fun|class|interface|object)\s+([A-Za-z_][\w]*)",
        "swift": r"\b(?:func|class|struct|protocol)\s+([A-Za-z_][\w]*)",
    }

    regex = regex_by_lang.get(language, r"\b([A-Za-z_][\w]*)\b")
    match = re.search(regex, snippet)
    if match:
        return _normalize_name(match.group(1))

    return ""


def _extract_signature(node: Any, source_bytes: bytes, language: Language) -> str:
    snippet = _node_text(node, source_bytes)
    if not snippet:
        return ""

    normalized = " ".join(snippet.strip().split())
    if not normalized:
        return ""

    if language == "python":
        idx = normalized.find(":")
        if idx != -1:
            return normalized[: idx + 1]
        return normalized[:200]

    for marker in ("{", "=>", " where "):
        idx = normalized.find(marker)
        if idx > 0:
            return normalized[:idx].strip()

    return normalized[:220]


def _extract_docstring(node: Any, source_bytes: bytes, language: Language) -> str | None:
    snippet = _node_text(node, source_bytes)
    if not snippet:
        return None

    if language == "python":
        match = re.search(r'\A[\s\S]*?:\s*(?:\n\s*)?("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', snippet)
        if match:
            return _strip_quotes(match.group(1))

    if language in {"javascript", "typescript", "java", "c", "cpp", "csharp", "php", "kotlin", "swift"}:
        doc = _extract_leading_comment(node, source_bytes)
        if doc:
            return doc

    if language in {"rust", "go"}:
        doc = _extract_leading_line_comments(node, source_bytes)
        if doc:
            return doc

    return None


def _extract_leading_comment(node: Any, source_bytes: bytes) -> str | None:
    start = int(getattr(node, "start_byte", 0))
    lookback_start = max(0, start - 1200)
    prefix = source_bytes[lookback_start:start].decode("utf-8", errors="replace")
    block = re.search(r"/\*\*([\s\S]*?)\*/\s*$", prefix)
    if block:
        return " ".join(block.group(1).split())
    return None


def _extract_leading_line_comments(node: Any, source_bytes: bytes) -> str | None:
    start = int(getattr(node, "start_byte", 0))
    lookback_start = max(0, start - 1000)
    prefix = source_bytes[lookback_start:start].decode("utf-8", errors="replace")
    comments = re.findall(r"(?:^|\n)\s*(?:///?\s?.+)", prefix)
    if not comments:
        return None
    joined = "\n".join(c.strip() for c in comments[-6:]).strip()
    return joined or None


def _strip_quotes(value: str) -> str:
    stripped = value.strip()
    for q in ('"""', "'''"):
        if stripped.startswith(q) and stripped.endswith(q):
            return stripped[len(q) : -len(q)].strip()
    return stripped


def _find_parent_name(node: Any, source_bytes: bytes, language: Language) -> str | None:
    mapping = ENTITY_NODE_TYPES.get(language, {})
    parent = getattr(node, "parent", None)

    while parent is not None:
        ptype = getattr(parent, "type", "")
        mapped = mapping.get(ptype)
        if mapped and mapped not in {EntityType.IMPORT, EntityType.EXPORT, EntityType.CONSTANT}:
            candidate = parent
            if language == "python" and ptype == "decorated_definition":
                candidate = _find_decorated_target(parent) or parent
            name = _extract_entity_name(candidate, source_bytes, language)
            if name:
                return name
        parent = getattr(parent, "parent", None)

    return None


def _extract_import_entities(node: Any, source_bytes: bytes, language: Language) -> list[EntityInfo]:
    snippet = _node_text(node, source_bytes)
    byte_range = _node_byte_range(node)
    line_range = _node_line_range(node)

    if not snippet.strip():
        return []

    if language == "python":
        imports = _parse_python_imports(snippet)
        if imports:
            return [
                EntityInfo(
                    name=name,
                    type=EntityType.IMPORT,
                    signature=f"import {name} from {source}",
                    byte_range=byte_range,
                    line_range=line_range,
                )
                for name, source in imports
            ]

    if language in {"javascript", "typescript"}:
        imports = _parse_ts_js_imports(snippet)
        if imports:
            return [
                EntityInfo(
                    name=name,
                    type=EntityType.IMPORT,
                    signature=f"import {name} from {source}",
                    byte_range=byte_range,
                    line_range=line_range,
                )
                for name, source in imports
            ]

    if language in {"rust", "go", "java", "c", "cpp", "csharp", "php", "kotlin", "swift"}:
        source_match = re.search(r"['\"]([^'\"]+)['\"]", snippet)
        source = source_match.group(1) if source_match else ""
        name_match = re.search(r"\b([A-Za-z_][\w]*)\b", snippet)
        if name_match:
            return [
                EntityInfo(
                    name=name_match.group(1),
                    type=EntityType.IMPORT,
                    signature=f"import {name_match.group(1)} from {source}".strip(),
                    byte_range=byte_range,
                    line_range=line_range,
                )
            ]

    return [
        EntityInfo(
            name="import",
            type=EntityType.IMPORT,
            signature=" ".join(snippet.split())[:220],
            byte_range=byte_range,
            line_range=line_range,
        )
    ]


def _parse_python_imports(snippet: str) -> list[tuple[str, str]]:
    text = " ".join(snippet.replace("\n", " ").split())
    out: list[tuple[str, str]] = []

    from_match = re.match(r"from\s+([A-Za-z0-9_\.]+)\s+import\s+(.+)", text)
    if from_match:
        source = from_match.group(1)
        symbols = from_match.group(2)
        for part in symbols.split(","):
            cleaned = part.strip()
            if not cleaned:
                continue
            alias_bits = cleaned.split(" as ")
            name = alias_bits[-1].strip() if len(alias_bits) > 1 else alias_bits[0].strip()
            if name == "*":
                name = source
            out.append((name, source))
        return out

    import_match = re.match(r"import\s+(.+)", text)
    if import_match:
        for part in import_match.group(1).split(","):
            cleaned = part.strip()
            if not cleaned:
                continue
            alias_bits = cleaned.split(" as ")
            raw_name = alias_bits[-1].strip() if len(alias_bits) > 1 else alias_bits[0].strip()
            name = raw_name.split(".")[0]
            out.append((name, raw_name))

    return out


def _parse_ts_js_imports(snippet: str) -> list[tuple[str, str]]:
    compact = " ".join(snippet.replace("\n", " ").split())
    source_match = re.search(r"from\s+['\"]([^'\"]+)['\"]", compact)
    source = source_match.group(1) if source_match else ""

    imports: list[tuple[str, str]] = []

    namespace_match = re.search(r"import\s+\*\s+as\s+([A-Za-z_$][\w$]*)", compact)
    if namespace_match:
        imports.append((namespace_match.group(1), source))

    default_match = re.search(r"import\s+([A-Za-z_$][\w$]*)\s*(?:,|from)", compact)
    if default_match and default_match.group(1) != "{" and default_match.group(1) != "*":
        imports.append((default_match.group(1), source))

    named_match = re.search(r"\{([^}]*)\}", compact)
    if named_match:
        for part in named_match.group(1).split(","):
            cleaned = part.strip()
            if not cleaned:
                continue
            alias_bits = re.split(r"\s+as\s+", cleaned)
            imports.append(((alias_bits[-1] if len(alias_bits) > 1 else alias_bits[0]).strip(), source))

    if not imports and source:
        imports.append((source.rsplit("/", 1)[-1], source))

    return imports


def _child_by_field_name(node: Any, field_name: str) -> Any | None:
    method = getattr(node, "child_by_field_name", None)
    if callable(method):
        try:
            return method(field_name)
        except Exception:
            return None
    return None


def _normalize_name(value: str) -> str:
    cleaned = value.strip().strip("`\"'")
    if "(" in cleaned:
        cleaned = cleaned.split("(", 1)[0]
    return cleaned.strip()


def _fallback_regex_entities(code: str, language: Language) -> list[EntityInfo]:
    if language != "python":
        return []

    entities: list[EntityInfo] = []

    for match in re.finditer(r"(?m)^\s*(from\s+[A-Za-z0-9_\.]+\s+import\s+.+|import\s+.+)$", code):
        line = match.group(1)
        imports = _parse_python_imports(line)
        line_start = code.count("\n", 0, match.start())
        line_end = line_start
        for name, source in imports:
            entities.append(
                EntityInfo(
                    name=name,
                    type=EntityType.IMPORT,
                    signature=f"import {name} from {source}",
                    byte_range=ByteRange(match.start(), match.end()),
                    line_range=LineRange(line_start, line_end),
                )
            )

    for match in re.finditer(r"(?m)^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)\s*\(", code):
        name = match.group(1)
        start = match.start()
        end = _find_block_end(code, start)
        line_start = code.count("\n", 0, start)
        line_end = code.count("\n", 0, end)
        signature_line = code[start : code.find("\n", start) if "\n" in code[start:] else len(code)]
        entities.append(
            EntityInfo(
                name=name,
                type=EntityType.FUNCTION,
                signature=" ".join(signature_line.strip().split()),
                byte_range=ByteRange(start, end),
                line_range=LineRange(line_start, line_end),
            )
        )

    for match in re.finditer(r"(?m)^\s*class\s+([A-Za-z_][\w]*)\b", code):
        name = match.group(1)
        start = match.start()
        end = _find_block_end(code, start)
        line_start = code.count("\n", 0, start)
        line_end = code.count("\n", 0, end)
        signature_line = code[start : code.find("\n", start) if "\n" in code[start:] else len(code)]
        entities.append(
            EntityInfo(
                name=name,
                type=EntityType.CLASS,
                signature=" ".join(signature_line.strip().split()),
                byte_range=ByteRange(start, end),
                line_range=LineRange(line_start, line_end),
            )
        )

    entities = _dedupe_entities(entities)
    entities.sort(key=lambda e: ((e.byte_range.start if e.byte_range else 0), e.name))
    return entities


def _find_block_end(text: str, start: int) -> int:
    lines = text[start:].splitlines(keepends=True)
    if not lines:
        return start
    base_indent = len(lines[0]) - len(lines[0].lstrip())
    offset = start + len(lines[0])
    for line in lines[1:]:
        stripped = line.strip()
        if stripped and (len(line) - len(line.lstrip())) <= base_indent:
            break
        offset += len(line)
    return max(offset, start)


def _dedupe_entities(entities: list[EntityInfo]) -> list[EntityInfo]:
    seen: set[tuple[str, EntityType, int, int]] = set()
    out: list[EntityInfo] = []
    for entity in entities:
        br = entity.byte_range or ByteRange(0, 0)
        key = (entity.name, entity.type, br.start, br.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(entity)
    return out


def enrich_parent_links(entities: list[EntityInfo]) -> list[EntityInfo]:
    """Fill missing parent fields based on byte-range nesting."""
    sorted_entities = sorted(entities, key=lambda e: ((e.byte_range.start if e.byte_range else 0), -(e.byte_range.end if e.byte_range else 0)))
    out: list[EntityInfo] = []

    for idx, entity in enumerate(sorted_entities):
        if entity.parent or entity.byte_range is None:
            out.append(entity)
            continue

        parent_name: str | None = None
        for candidate in reversed(sorted_entities[:idx]):
            if candidate.byte_range is None:
                continue
            if (
                candidate.byte_range.start <= entity.byte_range.start
                and candidate.byte_range.end >= entity.byte_range.end
                and candidate.name != entity.name
                and candidate.type not in {EntityType.IMPORT, EntityType.EXPORT}
            ):
                parent_name = candidate.name
                break

        if parent_name:
            out.append(replace(entity, parent=parent_name))
        else:
            out.append(entity)

    out.sort(key=lambda e: ((e.byte_range.start if e.byte_range else 0), e.name))
    return out

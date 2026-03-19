from __future__ import annotations

import ast
import re
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from omnichunk.parser.languages import get_language
from omnichunk.parser.query_patterns import get_query_source
from omnichunk.types import ByteRange, EntityInfo, EntityType, Language, LineRange

_tree_sitter: Any | None
try:
    import tree_sitter as _tree_sitter_mod

    _tree_sitter = _tree_sitter_mod
except Exception:  # pragma: no cover
    _tree_sitter = None

_TSQuery: Any | None = getattr(_tree_sitter, "Query", None) if _tree_sitter is not None else None
_TSQueryCursor: Any | None = (
    getattr(_tree_sitter, "QueryCursor", None) if _tree_sitter is not None else None
)

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
        matched_nodes: list[tuple[Any, EntityType, Any | None]] = query_matches
    else:
        matched_nodes = []
        for node in _iter_ast_nodes(tree.root_node):
            node_type = getattr(node, "type", "")
            entity_type = mapping.get(node_type)
            if entity_type is None:
                continue
            matched_nodes.append((node, entity_type, None))

    for node, entity_type, captured_name_node in matched_nodes:
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

        name = _extract_entity_name(
            name_node,
            source_bytes,
            language,
            explicit_name_node=captured_name_node,
        )
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


def _collect_query_matches(
    language: Language, tree: Any | None
) -> list[tuple[Any, EntityType, Any | None]]:
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

    entity_nodes: list[tuple[Any, EntityType]] = []
    name_nodes: list[Any] = []
    for node, capture_name in captures:
        if capture_name == "name":
            name_nodes.append(node)
            continue

        entity_type = _QUERY_CAPTURE_ENTITY_TYPES.get(capture_name)
        if entity_type is None:
            continue
        entity_nodes.append((node, entity_type))

    out: list[tuple[Any, EntityType, Any | None]] = []
    seen: set[tuple[str, int, int]] = set()
    for node, entity_type in entity_nodes:
        start = int(getattr(node, "start_byte", 0))
        end = int(getattr(node, "end_byte", start))
        key = (entity_type.value, start, end)
        if key in seen:
            continue
        seen.add(key)

        name_node = _find_query_name_capture(node, name_nodes)
        out.append((node, entity_type, name_node))

    return out


def _find_query_name_capture(entity_node: Any, name_nodes: list[Any]) -> Any | None:
    entity_start = int(getattr(entity_node, "start_byte", 0))
    entity_end = int(getattr(entity_node, "end_byte", entity_start))

    best_node: Any | None = None
    best_key: tuple[int, int, int] | None = None

    for name_node in name_nodes:
        name_start = int(getattr(name_node, "start_byte", 0))
        name_end = int(getattr(name_node, "end_byte", name_start))
        if name_start < entity_start or name_end > entity_end:
            continue

        distance = _distance_to_ancestor(name_node, entity_node)
        if distance is None:
            continue

        key = (distance, name_start - entity_start, name_end - name_start)
        if best_key is None or key < best_key:
            best_key = key
            best_node = name_node

    if best_node is not None:
        return best_node

    fallback_node: Any | None = None
    fallback_key: tuple[int, int, int] | None = None
    for name_node in name_nodes:
        name_start = int(getattr(name_node, "start_byte", 0))
        name_end = int(getattr(name_node, "end_byte", name_start))
        if name_start < entity_start or name_end > entity_end:
            continue
        key = (0, abs(name_start - entity_start), name_end - name_start)
        if fallback_key is None or key < fallback_key:
            fallback_key = key
            fallback_node = name_node

    return fallback_node


def _distance_to_ancestor(node: Any, ancestor: Any) -> int | None:
    distance = 0
    current = node
    while current is not None:
        if current is ancestor:
            return distance
        current = getattr(current, "parent", None)
        distance += 1
    return None


def _compile_query(language_obj: Any, query_source: str) -> Any | None:
    if _TSQuery is not None:
        try:
            query_ctor: Any = _TSQuery
            return query_ctor(language_obj, query_source)
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

    if _TSQueryCursor is None:
        return []

    try:
        cursor = _TSQueryCursor(query)
    except Exception:
        return []

    captures_method = getattr(cursor, "captures", None)
    if callable(captures_method):
        try:
            raw = captures_method(root)
            captures = _normalize_query_captures(raw, query)
            if captures:
                return captures
        except Exception:
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


def _extract_entity_name(
    node: Any,
    source_bytes: bytes,
    language: Language,
    *,
    explicit_name_node: Any | None = None,
) -> str:
    if explicit_name_node is not None:
        explicit = _node_text(explicit_name_node, source_bytes).strip()
        if explicit:
            return _normalize_name(explicit)

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
        return _extract_signature_python(node, source_bytes)

    for marker in ("{", "=>", " where "):
        idx = normalized.find(marker)
        if idx > 0:
            return normalized[:idx].strip()

    return normalized[:220]


def _extract_signature_python(node: Any, source_bytes: bytes) -> str:
    body = None
    for child in getattr(node, "children", []) or []:
        ctype = getattr(child, "type", "")
        if ctype in ("block", "body", "suite"):
            body = child
            break

    if body is None:
        for field_name in ("body", "consequence"):
            candidate = _child_by_field_name(node, field_name)
            if candidate is not None:
                body = candidate
                break

    if body is not None:
        start = int(getattr(node, "start_byte", 0))
        body_start = int(getattr(body, "start_byte", start))
        sig = source_bytes[start:body_start].decode("utf-8", errors="replace")
        sig = " ".join(sig.strip().rstrip(":").split())
        if sig:
            return sig + ":"

    snippet = _node_text(node, source_bytes)
    if not snippet:
        return ""

    normalized = " ".join(snippet.strip().split())
    paren_depth = 0
    bracket_depth = 0
    for idx, ch in enumerate(normalized):
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        elif ch == "[":
            bracket_depth += 1
        elif ch == "]":
            bracket_depth -= 1
        elif ch == ":" and paren_depth == 0 and bracket_depth == 0:
            return normalized[: idx + 1]

    return normalized[:200]


def _extract_docstring(node: Any, source_bytes: bytes, language: Language) -> str | None:
    if language == "python":
        return _extract_python_docstring(node, source_bytes)

    if language in {
        "javascript",
        "typescript",
        "java",
        "c",
        "cpp",
        "csharp",
        "php",
        "kotlin",
        "swift",
    }:
        return _extract_leading_comment(node, source_bytes)

    if language in {"rust", "go"}:
        doc = _extract_leading_line_comments(node, source_bytes)
        if doc:
            return doc
        return _extract_leading_comment(node, source_bytes)

    return None


def _extract_python_docstring(node: Any, source_bytes: bytes) -> str | None:
    body = _child_by_field_name(node, "body")
    if body is None:
        for child in getattr(node, "children", []) or []:
            if getattr(child, "type", "") in {"block", "suite"}:
                body = child
                break

    if body is None:
        return None

    first_statement = _first_named_child(body)
    if first_statement is None:
        return None
    if getattr(first_statement, "type", "") != "expression_statement":
        return None

    literal = _first_descendant_by_type(first_statement, {"string", "concatenated_string"})
    if literal is not None:
        parsed = _parse_python_string_literal(_node_text(literal, source_bytes).strip())
        if parsed:
            return parsed

    return _parse_python_string_literal(_node_text(first_statement, source_bytes).strip())


def _first_named_child(node: Any) -> Any | None:
    named_children = list(getattr(node, "named_children", []) or [])
    if named_children:
        return named_children[0]

    for child in getattr(node, "children", []) or []:
        if getattr(child, "is_named", True):
            return child

    return None


def _first_descendant_by_type(node: Any, target_types: set[str]) -> Any | None:
    stack = [node]
    while stack:
        current = stack.pop()
        if getattr(current, "type", "") in target_types:
            return current
        children = list(getattr(current, "children", []) or [])
        for child in reversed(children):
            stack.append(child)
    return None


def _parse_python_string_literal(value: str) -> str | None:
    if not value:
        return None

    try:
        parsed = ast.parse(value, mode="eval")
    except SyntaxError:
        return None

    body = getattr(parsed, "body", None)
    if isinstance(body, ast.Constant) and isinstance(body.value, str):
        text = body.value.strip()
        return text or None
    return None


def _extract_leading_comment(node: Any, source_bytes: bytes) -> str | None:
    comments = _collect_adjacent_leading_comments(node, source_bytes)
    if not comments:
        return None

    for comment in reversed(comments):
        cleaned = _clean_block_comment(_node_text(comment, source_bytes).strip())
        if cleaned:
            return cleaned

    return None


def _extract_leading_line_comments(node: Any, source_bytes: bytes) -> str | None:
    comments = _collect_adjacent_leading_comments(node, source_bytes)
    if not comments:
        return None

    lines: list[str] = []
    for comment in comments:
        cleaned = _clean_line_comment(_node_text(comment, source_bytes).strip())
        if cleaned:
            lines.append(cleaned)

    if not lines:
        return None

    return "\n".join(lines)


def _collect_adjacent_leading_comments(node: Any, source_bytes: bytes) -> list[Any]:
    parent = getattr(node, "parent", None)
    if parent is None:
        return []

    siblings = list(getattr(parent, "children", []) or [])
    if not siblings:
        return []

    index = next((idx for idx, child in enumerate(siblings) if child is node), -1)
    if index < 0:
        return []

    comments: list[Any] = []
    cursor_start = int(getattr(node, "start_byte", 0))

    for sibling in reversed(siblings[:index]):
        sibling_start = int(getattr(sibling, "start_byte", 0))
        sibling_end = int(getattr(sibling, "end_byte", sibling_start))

        if sibling_end > cursor_start:
            continue

        gap = source_bytes[sibling_end:cursor_start]
        if gap.strip():
            break

        sibling_type = getattr(sibling, "type", "")
        if "comment" in sibling_type:
            comments.append(sibling)
            cursor_start = sibling_start
            continue

        sibling_slice = source_bytes[sibling_start:sibling_end]
        if sibling_slice.strip():
            break

        cursor_start = sibling_start

    comments.reverse()
    return comments


def _clean_block_comment(raw: str) -> str | None:
    value = raw.strip()
    if not value.startswith("/**") or not value.endswith("*/"):
        return None

    inner = value[3:-2]
    lines: list[str] = []
    for line in inner.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("*"):
            cleaned = cleaned[1:].strip()
        if cleaned:
            lines.append(cleaned)

    if lines:
        return "\n".join(lines)

    single_line = inner.strip()
    return single_line or None


def _clean_line_comment(raw: str) -> str | None:
    value = raw.strip()
    if value.startswith("///") or value.startswith("//!"):
        cleaned = value[3:].strip()
        return cleaned or None
    if value.startswith("//"):
        cleaned = value[2:].strip()
        return cleaned or None
    return None


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


def _extract_import_entities(
    node: Any, source_bytes: bytes, language: Language
) -> list[EntityInfo]:
    snippet = _node_text(node, source_bytes)
    byte_range = _node_byte_range(node)
    line_range = _node_line_range(node)

    if not snippet.strip():
        return []

    imports: list[tuple[str, str]] = []

    if language == "python":
        imports = _parse_python_imports(snippet)
    elif language in {"javascript", "typescript"}:
        imports = _parse_ts_js_imports(snippet)
    elif language == "rust":
        imports = _parse_rust_imports(snippet)
    elif language == "go":
        imports = _parse_go_imports(snippet)
    elif language == "java":
        imports = _parse_java_imports(snippet)
    elif language in {"c", "cpp", "csharp", "php", "kotlin", "swift"}:
        source_match = re.search(r"['\"]([^'\"]+)['\"]", snippet)
        source = source_match.group(1) if source_match else ""
        name_match = re.search(r"\b([A-Za-z_][\w]*)\b", snippet)
        if name_match:
            imports = [(name_match.group(1), source)]

    if imports:
        entities = _build_import_entities(imports, byte_range, line_range)
        if entities:
            return entities

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


def _build_import_entities(
    imports: list[tuple[str, str]],
    byte_range: ByteRange,
    line_range: LineRange,
) -> list[EntityInfo]:
    entities: list[EntityInfo] = []
    seen: set[tuple[str, str]] = set()

    for name, source in imports:
        clean_name = name.strip()
        clean_source = source.strip()
        if not clean_name:
            continue

        key = (clean_name, clean_source)
        if key in seen:
            continue
        seen.add(key)

        signature = (
            f"import {clean_name} from {clean_source}"
            if clean_source
            else f"import {clean_name}"
        )
        entities.append(
            EntityInfo(
                name=clean_name,
                type=EntityType.IMPORT,
                signature=signature,
                byte_range=byte_range,
                line_range=line_range,
            )
        )

    return entities


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
            imports.append(
                ((alias_bits[-1] if len(alias_bits) > 1 else alias_bits[0]).strip(), source)
            )

    if not imports and source:
        imports.append((source.rsplit("/", 1)[-1], source))

    return imports


def _parse_rust_imports(snippet: str) -> list[tuple[str, str]]:
    text = " ".join(snippet.replace("\n", " ").split())
    use_match = re.match(r"(?:pub\s+)?use\s+(.+?)\s*;?$", text)
    if not use_match:
        return []

    expanded = _expand_rust_use_paths(use_match.group(1).strip())
    imports: list[tuple[str, str]] = []

    for raw_path in expanded:
        cleaned = raw_path.strip()
        if not cleaned:
            continue

        alias_match = re.search(r"\s+as\s+([A-Za-z_][\w]*)$", cleaned)
        if alias_match:
            source = cleaned[: alias_match.start()].strip()
            name = alias_match.group(1)
        else:
            source = cleaned
            leaf = source.split("::")[-1]
            if leaf == "self":
                source = "::".join(source.split("::")[:-1])
                leaf = source.split("::")[-1] if source else ""
            name = leaf or source

        if source:
            imports.append((name, source))

    return imports


def _expand_rust_use_paths(path_expr: str) -> list[str]:
    path = path_expr.strip()
    if not path:
        return []

    brace_start = path.find("{")
    if brace_start < 0:
        return [path]

    brace_end = _find_matching_brace(path, brace_start)
    if brace_end < 0:
        return [path]

    prefix = path[:brace_start].strip()
    inside = path[brace_start + 1 : brace_end]
    suffix = path[brace_end + 1 :].strip()

    if prefix.endswith("::"):
        prefix = prefix[:-2]
    if suffix.startswith("::"):
        suffix = suffix[2:]

    expanded: list[str] = []
    for part in _split_top_level_csv(inside):
        piece = part.strip()
        if not piece:
            continue

        combined = _join_rust_path(prefix, piece)
        if suffix:
            combined = _join_rust_path(combined, suffix)

        expanded.extend(_expand_rust_use_paths(combined))

    return expanded or [path]


def _find_matching_brace(text: str, start: int) -> int:
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _split_top_level_csv(value: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0

    for idx, ch in enumerate(value):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append(value[start:idx])
            start = idx + 1

    parts.append(value[start:])
    return parts


def _join_rust_path(prefix: str, suffix: str) -> str:
    left = prefix.strip()
    right = suffix.strip()
    if not left:
        return right
    if not right:
        return left
    if left.endswith("::") or right.startswith("::"):
        return f"{left}{right}"
    return f"{left}::{right}"


def _parse_go_imports(snippet: str) -> list[tuple[str, str]]:
    text = snippet.strip()
    if not text:
        return []

    specs: list[str] = []
    block_match = re.search(r"import\s*\((?P<body>[\s\S]*?)\)", text)
    if block_match:
        specs = [line.strip() for line in block_match.group("body").splitlines()]
    else:
        single = re.match(r"import\s+(.+)$", " ".join(text.split()))
        if single:
            specs = [single.group(1).strip()]

    imports: list[tuple[str, str]] = []
    for spec in specs:
        cleaned = spec.split("//", 1)[0].strip()
        if not cleaned:
            continue

        match = re.match(
            r'(?:(?P<alias>[A-Za-z_\.][\w\.]*)\s+)?(?P<q>["`])(?P<source>[^"`]+)(?P=q)',
            cleaned,
        )
        if not match:
            continue

        source = match.group("source").strip()
        alias = (match.group("alias") or "").strip()
        if not source:
            continue

        name = alias if alias and alias not in {"_", "."} else source.rsplit("/", 1)[-1]

        imports.append((name, source))

    return imports


def _parse_java_imports(snippet: str) -> list[tuple[str, str]]:
    imports: list[tuple[str, str]] = []
    pattern = r"import\s+(?:static\s+)?([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*|\.\*)*)\s*;?"

    for match in re.finditer(pattern, snippet):
        source = match.group(1).strip()
        if not source:
            continue

        if source.endswith(".*"):
            package = source[:-2]
            name = package.split(".")[-1] if package else source
        else:
            name = source.split(".")[-1]

        imports.append((name, source))

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

    newline_offsets = _collect_newline_offsets(code)
    code_len = len(code)

    entities: list[EntityInfo] = []

    for match in re.finditer(r"(?m)^\s*(from\s+[A-Za-z0-9_\.]+\s+import\s+.+|import\s+.+)$", code):
        line = match.group(1)
        imports = _parse_python_imports(line)
        start = match.start()
        end = match.end()
        line_start = _line_for_char_offset(newline_offsets, start)
        line_end = line_start
        for name, source in imports:
            entities.append(
                EntityInfo(
                    name=name,
                    type=EntityType.IMPORT,
                    signature=f"import {name} from {source}",
                    byte_range=ByteRange(start, end),
                    line_range=LineRange(line_start, line_end),
                )
            )

    for match in re.finditer(r"(?m)^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)\s*\(", code):
        name = match.group(1)
        start = match.start()
        end = _find_block_end(code, start)
        line_start = _line_for_char_offset(newline_offsets, start)
        line_end = _line_for_char_offset(newline_offsets, end)
        signature_end = code.find("\n", start)
        if signature_end < 0:
            signature_end = code_len
        signature_line = code[start:signature_end]
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
        line_start = _line_for_char_offset(newline_offsets, start)
        line_end = _line_for_char_offset(newline_offsets, end)
        signature_end = code.find("\n", start)
        if signature_end < 0:
            signature_end = code_len
        signature_line = code[start:signature_end]
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
    text_len = len(text)
    if start < 0:
        start = 0
    if start >= text_len:
        return start

    first_line_end = text.find("\n", start)
    if first_line_end < 0:
        return text_len

    base_indent = _leading_indent(text[start:first_line_end])
    offset = first_line_end + 1

    cursor = offset
    while cursor < text_len:
        line_end = text.find("\n", cursor)
        if line_end < 0:
            line_end = text_len
            next_cursor = text_len
        else:
            next_cursor = line_end + 1

        line = text[cursor:line_end]
        stripped = line.strip()
        if stripped and _leading_indent(line) <= base_indent:
            break

        offset = next_cursor
        cursor = next_cursor

    return max(offset, start)


def _leading_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _collect_newline_offsets(text: str) -> list[int]:
    return [idx for idx, ch in enumerate(text) if ch == "\n"]


def _line_for_char_offset(newline_offsets: list[int], offset: int) -> int:
    if offset <= 0:
        return 0
    return bisect_right(newline_offsets, offset - 1)


def _dedupe_entities(entities: list[EntityInfo]) -> list[EntityInfo]:
    seen: set[tuple[str, str, int, int]] = set()
    out: list[EntityInfo] = []
    for entity in entities:
        br = entity.byte_range or ByteRange(0, 0)
        key = (entity.name, entity.type.value, br.start, br.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(entity)
    return out


def enrich_parent_links(entities: list[EntityInfo]) -> list[EntityInfo]:
    """Fill missing parent fields based on byte-range nesting."""
    sorted_entities = sorted(
        entities,
        key=lambda e: (
            (e.byte_range.start if e.byte_range else 0),
            -(e.byte_range.end if e.byte_range else 0),
        ),
    )
    out: list[EntityInfo] = []
    stack: list[EntityInfo] = []

    for entity in sorted_entities:
        byte_range = entity.byte_range
        if byte_range is None:
            out.append(entity)
            continue

        while stack:
            top_range = stack[-1].byte_range
            if top_range is None or top_range.end <= byte_range.start:
                stack.pop()
                continue
            break

        enriched = entity
        if not entity.parent:
            parent_name: str | None = None
            for candidate in reversed(stack):
                candidate_range = candidate.byte_range
                if candidate_range is None:
                    continue
                if (
                    candidate_range.start <= byte_range.start
                    and candidate_range.end >= byte_range.end
                    and candidate.name != entity.name
                    and candidate.type.value not in {"import", "export"}
                ):
                    parent_name = candidate.name
                    break

            if parent_name:
                enriched = replace(entity, parent=parent_name)

        out.append(enriched)
        stack.append(enriched)

    out.sort(key=lambda e: ((e.byte_range.start if e.byte_range else 0), e.name))
    return out

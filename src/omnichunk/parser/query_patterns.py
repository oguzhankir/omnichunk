from __future__ import annotations

from omnichunk.types import Language

_QUERY_SOURCES: dict[Language, str] = {
    "python": """
(function_definition name: (_) @name) @entity.function
(class_definition name: (_) @name) @entity.class
(import_statement) @entity.import
(import_from_statement) @entity.import
(decorated_definition
  [
    (function_definition name: (_) @name)
    (class_definition name: (_) @name)
  ]) @entity.decorator
""",
    "javascript": """
(function_declaration name: (_) @name) @entity.function
(method_definition name: (_) @name) @entity.method
(class_declaration name: (_) @name) @entity.class
(import_statement) @entity.import
(export_statement) @entity.export
""",
    "typescript": """
(function_declaration name: (_) @name) @entity.function
(method_definition name: (_) @name) @entity.method
(class_declaration name: (_) @name) @entity.class
(interface_declaration name: (_) @name) @entity.interface
(type_alias_declaration name: (_) @name) @entity.type
(enum_declaration name: (_) @name) @entity.enum
(import_statement) @entity.import
(export_statement) @entity.export
""",
    "rust": """
(function_item name: (_) @name) @entity.function
(impl_item type: (_) @name) @entity.class
(struct_item name: (_) @name) @entity.class
(trait_item name: (_) @name) @entity.interface
(enum_item name: (_) @name) @entity.enum
(use_declaration) @entity.import
""",
    "go": """
(function_declaration name: (_) @name) @entity.function
(method_declaration name: (_) @name) @entity.method
(type_declaration (type_spec name: (_) @name)) @entity.type
(import_declaration) @entity.import
""",
    "java": """
(method_declaration name: (_) @name) @entity.method
(class_declaration name: (_) @name) @entity.class
(interface_declaration name: (_) @name) @entity.interface
(enum_declaration name: (_) @name) @entity.enum
(import_declaration) @entity.import
""",
    "c": """
(function_definition declarator: (_) @name) @entity.function
(declaration declarator: (_) @name) @entity.type
(preproc_include) @entity.import
""",
    "cpp": """
(function_definition declarator: (_) @name) @entity.function
(class_specifier name: (_) @name) @entity.class
(struct_specifier name: (_) @name) @entity.class
(preproc_include) @entity.import
""",
    "csharp": """
(method_declaration name: (_) @name) @entity.method
(class_declaration name: (_) @name) @entity.class
(interface_declaration name: (_) @name) @entity.interface
(enum_declaration name: (_) @name) @entity.enum
(using_directive) @entity.import
""",
    "ruby": """
(method name: (_) @name) @entity.method
(class name: (_) @name) @entity.class
(module name: (_) @name) @entity.class
""",
    "php": """
(function_definition name: (_) @name) @entity.function
(method_declaration name: (_) @name) @entity.method
(class_declaration name: (_) @name) @entity.class
(interface_declaration name: (_) @name) @entity.interface
(trait_declaration name: (_) @name) @entity.type
(namespace_use_declaration) @entity.import
""",
    "kotlin": """
(function_declaration name: (_) @name) @entity.function
(class_declaration name: (_) @name) @entity.class
(object_declaration name: (_) @name) @entity.class
(interface_declaration name: (_) @name) @entity.interface
(import_header) @entity.import
""",
    "swift": """
(function_declaration name: (_) @name) @entity.function
(class_declaration name: (_) @name) @entity.class
(struct_declaration name: (_) @name) @entity.class
(protocol_declaration name: (_) @name) @entity.interface
(import_declaration) @entity.import
""",
}


def get_query_source(language: Language) -> str | None:
    source = _QUERY_SOURCES.get(language)
    if not source:
        return None
    return source.strip()

from __future__ import annotations

from omnichunk.types import Language

_QUERY_SOURCES: dict[Language, str] = {
    "python": """
(function_definition) @entity.function
(class_definition) @entity.class
(import_statement) @entity.import
(import_from_statement) @entity.import
(decorated_definition) @entity.decorator
""",
    "javascript": """
(function_declaration) @entity.function
(method_definition) @entity.method
(class_declaration) @entity.class
(import_statement) @entity.import
(export_statement) @entity.export
""",
    "typescript": """
(function_declaration) @entity.function
(method_definition) @entity.method
(class_declaration) @entity.class
(interface_declaration) @entity.interface
(type_alias_declaration) @entity.type
(enum_declaration) @entity.enum
(import_statement) @entity.import
(export_statement) @entity.export
""",
    "rust": """
(function_item) @entity.function
(struct_item) @entity.class
(trait_item) @entity.interface
(enum_item) @entity.enum
(use_declaration) @entity.import
""",
    "go": """
(function_declaration) @entity.function
(method_declaration) @entity.method
(type_declaration) @entity.type
(import_declaration) @entity.import
""",
    "java": """
(method_declaration) @entity.method
(class_declaration) @entity.class
(interface_declaration) @entity.interface
(enum_declaration) @entity.enum
(import_declaration) @entity.import
""",
    "c": """
(function_definition) @entity.function
(declaration) @entity.type
(preproc_include) @entity.import
""",
    "cpp": """
(function_definition) @entity.function
(class_specifier) @entity.class
(struct_specifier) @entity.class
(preproc_include) @entity.import
""",
    "csharp": """
(method_declaration) @entity.method
(class_declaration) @entity.class
(interface_declaration) @entity.interface
(enum_declaration) @entity.enum
(using_directive) @entity.import
""",
    "ruby": """
(method) @entity.method
(class) @entity.class
(module) @entity.class
""",
    "php": """
(function_definition) @entity.function
(method_declaration) @entity.method
(class_declaration) @entity.class
(interface_declaration) @entity.interface
(trait_declaration) @entity.type
(namespace_use_declaration) @entity.import
""",
    "kotlin": """
(function_declaration) @entity.function
(class_declaration) @entity.class
(object_declaration) @entity.class
(interface_declaration) @entity.interface
(import_header) @entity.import
""",
    "swift": """
(function_declaration) @entity.function
(class_declaration) @entity.class
(struct_declaration) @entity.class
(protocol_declaration) @entity.interface
(import_declaration) @entity.import
""",
}


def get_query_source(language: Language) -> str | None:
    source = _QUERY_SOURCES.get(language)
    if not source:
        return None
    return source.strip()

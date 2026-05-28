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
(assignment
  left: (identifier) @name
  (#eq? @name "__all__")) @entity.module_export
(assignment
  left: (identifier) @name
  type: (type) @ann
  (#eq? @ann "TypeAlias")) @entity.type_alias
(class_definition
  name: (_) @name
  superclasses: (argument_list (identifier) @base
                               (#eq? @base "Protocol"))) @entity.protocol
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
(module name: (_) @name) @entity.module
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
(struct_specifier name: (_) @name) @entity.class
(type_definition) @entity.type
(preproc_include) @entity.import
""",
    "cpp": """
(function_definition declarator: (_) @name) @entity.function
(class_specifier name: (_) @name) @entity.class
(struct_specifier name: (_) @name) @entity.class
(namespace_definition name: (_) @name) @entity.class
(type_definition) @entity.type
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
    "sql": """
(create_table (object_reference) @name) @entity.sql_object
(create_view (object_reference) @name) @entity.sql_object
(create_function (object_reference) @name) @entity.function
(create_index (identifier) @name) @entity.sql_object
""",
    "bash": """
(function_definition name: (_) @name) @entity.function
""",
    "scala": """
(object_definition name: (_) @name) @entity.class
(class_definition name: (_) @name) @entity.class
(trait_definition name: (_) @name) @entity.interface
(function_definition name: (_) @name) @entity.function
(import_declaration) @entity.import
""",
    "elixir": """
(call target: (identifier) @kind
      (arguments (alias) @name)
      (#eq? @kind "defmodule")) @entity.class
(call target: (identifier) @kind
      (#match? @kind "^(def|defp)$")) @entity.function
(call target: (identifier) @kind
      (#match? @kind "^(defmacro|defmacrop)$")) @entity.macro
(call target: (identifier) @kind
      (#match? @kind "^(use|import|alias|require)$")) @entity.import
""",
}


def get_query_source(language: Language) -> str | None:
    source = _QUERY_SOURCES.get(language)
    if not source:
        return None
    return source.strip()

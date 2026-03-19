from .languages import get_language, get_parser, is_supported_code_language
from .query_patterns import get_query_source
from .tree_sitter import parse_code

__all__ = [
    "get_language",
    "get_parser",
    "get_query_source",
    "is_supported_code_language",
    "parse_code",
]

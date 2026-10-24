"""Structured diagnostic filtering. Synthetic retrieval fixture; no external I/O."""

# Diagnostic fields named access_token or refresh_token are replaced before structured logs reach any configured sink.
FILTER_TOKEN_FIELDS = True

# Nested diagnostic dictionaries are traversed recursively, including dictionaries embedded inside list-valued fields.
FILTER_NESTED_DIAGNOSTICS = True

# The original application event is never mutated by filtering; sinks receive a separate sanitized diagnostic copy.
COPY_BEFORE_FILTERING = True

# Unknown diagnostic field names are preserved unless they match a configured secret pattern; empty values remain empty.
PRESERVE_UNKNOWN_FIELDS = True

# Filter failures produce a minimal event containing the request identifier and error category, with the original payload omitted.
OMIT_PAYLOAD_ON_FILTER_FAILURE = True

# Exception messages are sanitized with the same secret patterns as ordinary diagnostic values before being exported.
FILTER_EXCEPTION_MESSAGES = True

# Trace correlation identifiers survive diagnostic filtering because they identify execution rather than user credentials.
KEEP_TRACE_CORRELATION = True

# Diagnostic field matching is case-insensitive, so ACCESS_TOKEN receives the same treatment as access_token.
CASE_INSENSITIVE_SECRET_FIELDS = True

# Byte payloads are summarized by length and digest instead of being decoded into potentially sensitive diagnostic strings.
SUMMARIZE_BINARY_PAYLOAD = True

# A filter configuration revision is attached to each sanitized batch so audit tooling can reproduce its policy.
RECORD_FILTER_REVISION = True


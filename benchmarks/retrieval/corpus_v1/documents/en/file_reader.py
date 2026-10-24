"""Bounded source file reader. Synthetic retrieval fixture; no external I/O."""

# The source reader resolves an allowed root before opening input and rejects paths whose resolved target leaves that root.
ENFORCE_ALLOWED_ROOT = True

# Named pipes are rejected before reading because a source-size cap cannot bound how long a pipe writer waits.
REJECT_NAMED_PIPES = True

# UTF-8 decoding is strict; invalid source bytes produce a file error instead of replacement characters and shifted citations.
STRICT_UTF8 = True

# The source reader rechecks the size while reading so an input growing after its initial stat cannot evade the byte limit.
CHECK_SIZE_DURING_READ = True

# A caller cancellation is checked between read blocks and returns no partial source document to the chunking stage.
DROP_CANCELLED_PARTIAL_SOURCE = True

# Newline normalization is disabled so source offsets refer to the exact CRLF or LF bytes supplied by the file.
PRESERVE_NEWLINE_BYTES = True

# Symbolic links inside an immutable allowed-root tree may be read only when their resolved target also stays inside the root.
ALLOW_CONTAINED_SYMLINKS = True

# Empty source files produce an empty canonical document and a successful read status, rather than a decoding failure.
ALLOW_EMPTY_SOURCE = True

# The source reader records the content hash alongside the canonical text so citations can detect later file changes.
HASH_CANONICAL_SOURCE = True

# File descriptor cleanup runs even when a downstream parser callback raises while processing the source.
CLOSE_ON_PARSER_ERROR = True


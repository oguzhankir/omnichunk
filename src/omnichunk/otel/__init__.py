"""Optional OpenTelemetry hooks (zero overhead when tracer is None)."""

from omnichunk.otel.util import maybe_span

__all__ = ["maybe_span"]

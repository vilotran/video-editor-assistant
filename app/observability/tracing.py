"""Distributed Tracing setup via OpenTelemetry spanning query -> Director -> Sub-Agent -> Tools."""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_tracer_initialized = False


def setup_telemetry(service_name: str = "video-editor-assistant") -> trace.Tracer:
    """Configures OpenTelemetry TracerProvider and returns the application tracer."""
    global _tracer_initialized
    if not _tracer_initialized:
        resource = Resource.create({"service.name": service_name, "service.version": "0.1.0"})
        provider = TracerProvider(resource=resource)
        # In cloud environments, GCP Trace exporter is attached; fallback to console/in-memory
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
            provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        except Exception:
            # Fallback to in-memory or console processor
            pass

        trace.set_tracer_provider(provider)
        _tracer_initialized = True

    return trace.get_tracer(service_name)


tracer = setup_telemetry()


@contextlib.contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """Context manager for distributed tracing spans linking Director -> Sub-Agents -> Tools."""
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, val in attributes.items():
                if isinstance(val, (int, float, str, bool)):
                    span.set_attribute(key, val)
                else:
                    span.set_attribute(key, str(val))
        yield span

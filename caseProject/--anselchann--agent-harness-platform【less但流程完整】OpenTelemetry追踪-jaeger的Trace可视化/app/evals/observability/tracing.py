"""
OpenTelemetry tracing setup for the Agent Harness Platform.

Provides:
- TracerProvider with console + OTLP exporters
- In-memory span store for trace API queries
- Helper to create spans across the platform

Span hierarchy (per the blueprint):
    run
    ├─ prepare_context
    ├─ plan
    │  └─ llm_call
    ├─ invoke_tool
    │  └─ mcp_call
    ├─ synthesize_answer
    │  └─ llm_call
    └─ validate_output
"""

from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

from app.config import settings

# ── In-memory span store (for trace API queries) ──
_trace_store: dict[str, list[dict]] = {}  # run_id → list of span dicts


def _store_span(span_dict: dict) -> None:
    run_id = span_dict.get("run_id")
    if run_id:
        _trace_store.setdefault(run_id, []).append(span_dict)


def get_trace(run_id: str) -> dict | None:
    """Return the collected trace for a run."""
    spans = _trace_store.get(run_id)
    if not spans:
        return None
    root = next((s for s in spans if s.get("parent_id") is None), spans[0])
    return {
        "trace_id": root.get("trace_id", ""),
        "run_id": run_id,
        "spans": sorted(spans, key=lambda s: s.get("start_time", "")),
        "span_count": len(spans),
    }


# ── OTel setup ──
_resource = Resource.create({"service.name": settings.app_name})

_provider = TracerProvider(resource=_resource)

# Always add console exporter for dev visibility
_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

# Add OTLP exporter if endpoint is explicitly configured and reachable
if settings.otel_endpoint:
    try:
        otlp = OTLPSpanExporter(endpoint=settings.otel_endpoint)
        _provider.add_span_processor(BatchSpanProcessor(otlp))
    except Exception:
        pass

trace.set_tracer_provider(_provider)

_otel_tracer = trace.get_tracer(settings.app_name, "0.1.0")


def get_tracer():
    return _otel_tracer


# ── Span creation helper ──
@contextmanager
def start_span(
    name: str,
    run_id: str | None = None,
    parent_ctx: trace.Context | None = None,
    attrs: dict | None = None,
) -> Iterator["trace.Span"]:
    """Create a new span, store it, and yield it for use as a context manager."""
    span_attrs = dict(attrs or {})
    if run_id:
        span_attrs["run_id"] = run_id

    span = _otel_tracer.start_span(name, context=parent_ctx, attributes=span_attrs)
    ctx = trace.set_span_in_context(span)

    span_id_int = span.get_span_context().span_id
    trace_id_int = span.get_span_context().trace_id
    parent_id_int = None
    if parent_ctx:
        parent_span = getattr(parent_ctx, "_span", None)
        if parent_span is not None:
            parent_id_int = parent_span.get_span_context().span_id

    span_record = {
        "span_id": format(span_id_int, "016x"),
        "trace_id": format(trace_id_int, "032x"),
        "parent_id": format(parent_id_int, "016x") if parent_id_int else None,
        "run_id": run_id,
        "name": name,
        "start_time": str(span.start_time) if span.start_time else "",
        "attributes": dict(span_attrs),
    }

    try:
        yield span
    except Exception as exc:
        span.record_exception(exc)
        span_record["error"] = str(exc)
        raise
    finally:
        span.end()
        span_record["duration_ms"] = int(span.end_time - span.start_time) / 1e6 if span.end_time and span.start_time else 0
        _store_span(span_record)


class SpanContext:
    """Holds the OTel context for a span, for passing to child spans."""
    def __init__(self, span: trace.Span):
        self.ctx = trace.set_span_in_context(span)

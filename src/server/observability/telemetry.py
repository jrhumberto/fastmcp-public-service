"""
OpenTelemetry setup for MCP server observability.
Provides distributed tracing and metrics for all tool calls.
Supports OTLP export (production) and console export (local dev / tests).
"""

import logging
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter

logger = logging.getLogger(__name__)


@dataclass
class Telemetry:
    tracer: trace.Tracer
    tool_calls: metrics.Counter
    tool_errors: metrics.Counter
    tool_duration: metrics.Histogram
    db_pool_size: metrics.ObservableGauge


def setup_telemetry(
    service_name: str,
    *,
    otel_enabled: bool = True,
    otlp_endpoint: str = "http://localhost:4317",
) -> Telemetry:
    """
    Initialize OpenTelemetry tracing and metrics.

    Args:
        service_name: Identifies this service in traces and metrics.
        otel_enabled: When True, export via OTLP gRPC (production collectors).
                      When False, export to console (local dev / tests).
        otlp_endpoint: OTLP gRPC collector endpoint. Only used when otel_enabled=True.
                       Unreachable endpoints are handled silently — the SDK buffers
                       and retries without blocking server startup.
    """
    resource = Resource.create({"service.name": service_name})

    span_exporter: SpanExporter
    metric_exporter: MetricExporter

    if otel_enabled:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
        logger.info("OpenTelemetry OTLP exporter: %s", otlp_endpoint)
    else:
        span_exporter = ConsoleSpanExporter()
        metric_exporter = ConsoleMetricExporter()
        logger.info("OpenTelemetry console exporter enabled (dev/test mode)")

    # Tracing
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=30000
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    tracer = trace.get_tracer(service_name)
    meter = metrics.get_meter(service_name)

    def _pool_size_callback(options: CallbackOptions) -> list[Any]:
        """
        Live pool size gauge — called by the metrics SDK at each export interval.
        Late-binds to get_pool() so the callback works even though the pool is
        initialized after setup_telemetry() runs.
        """
        try:
            from ..db.pool import get_pool  # lazy: avoids circular import at module load

            asyncpg_pool = get_pool()._pool
            if asyncpg_pool is not None:
                return [Observation(asyncpg_pool.get_size())]
        except RuntimeError:
            pass  # pool not yet initialized — skip this observation cycle
        return []

    logger.info("OpenTelemetry initialized for service: %s", service_name)

    return Telemetry(
        tracer=tracer,
        tool_calls=meter.create_counter(
            "mcp.tool.calls",
            description="Total number of MCP tool invocations",
        ),
        tool_errors=meter.create_counter(
            "mcp.tool.errors",
            description="Total number of MCP tool errors",
        ),
        tool_duration=meter.create_histogram(
            "mcp.tool.duration",
            unit="ms",
            description="MCP tool execution duration in milliseconds",
        ),
        db_pool_size=meter.create_observable_gauge(
            "mcp.db.pool_size",
            callbacks=[_pool_size_callback],
            description="Current DB connection pool size",
        ),
    )

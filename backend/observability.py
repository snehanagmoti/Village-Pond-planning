"""OpenTelemetry traces, metrics and logs for the pond-planning API.

Telemetry is opt-in: set ``OTEL_ENABLED=true`` and point
``OTEL_EXPORTER_OTLP_ENDPOINT`` at an OpenTelemetry Collector (default
``http://localhost:4318``). When disabled, or when the OpenTelemetry packages
are not installed (for example on an older lab deployment), every helper here
is a cheap no-op so the application behaves exactly as before.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

try:  # The API package is tiny; the SDK and exporters are only needed when enabled.
    from opentelemetry import metrics, trace
    from opentelemetry.trace import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on hosts without OpenTelemetry
    _OTEL_AVAILABLE = False

SERVICE_NAME = "village-pond-api"
_state: dict[str, Any] = {"enabled": False}


def telemetry_enabled() -> bool:
    return bool(_state["enabled"])


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().casefold() in {"1", "true", "yes", "on"}


# Default OpenTelemetry buckets (0, 5, 10, 25 ... 10000) suit milliseconds; analyses take
# 0.1-60 s, so second-scale boundaries are needed for meaningful percentiles.
_SECONDS_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 1.5, 2, 3, 5, 10, 30, 60]


class _Instruments:
    """Custom application metrics (created lazily so the no-op path stays free)."""

    def __init__(self) -> None:
        meter = metrics.get_meter(SERVICE_NAME, "2.0.0")
        self.requests = meter.create_counter(
            "pond.analysis.requests", unit="{request}",
            description="Pond analyses by workflow, selection mode and outcome",
        )
        self.duration = meter.create_histogram(
            "pond.analysis.duration", unit="s",
            description="End-to-end analysis time per workflow",
            explicit_bucket_boundaries_advisory=_SECONDS_BUCKETS,
        )
        self.stage_duration = meter.create_histogram(
            "pond.pipeline.stage.duration", unit="s",
            description="Time spent in each terrain/hydrology pipeline stage",
            explicit_bucket_boundaries_advisory=_SECONDS_BUCKETS,
        )
        self.catchment_area = meter.create_histogram(
            "pond.catchment.area", unit="ha",
            description="Catchment area of the selected pond point",
            explicit_bucket_boundaries_advisory=[1, 5, 10, 25, 50, 75, 100, 200, 500, 1000],
        )
        self.runoff_volume = meter.create_histogram(
            "pond.runoff.volume", unit="m3",
            description="Estimated annual runoff volume (C x P x A)",
            explicit_bucket_boundaries_advisory=[1e3, 1e4, 5e4, 1e5, 2e5, 5e5, 1e6, 5e6],
        )
        self.source_failures = meter.create_counter(
            "pond.external_source.failures", unit="{failure}",
            description="Failures of external data sources (imagery, hydrography, rainfall, elevation)",
        )


def setup_observability(app) -> bool:
    """Configure providers, exporters and auto-instrumentation once per process."""
    if _state["enabled"] or not _flag("OTEL_ENABLED"):
        return telemetry_enabled()
    if not _OTEL_AVAILABLE:
        logger.warning("otel_disabled reason=packages_missing")
        return False
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:  # pragma: no cover
        logger.warning("otel_disabled reason=%s", exc)
        return False

    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", SERVICE_NAME),
        "service.version": "2.0.0",
        "deployment.environment": os.getenv("APP_ENV", "development"),
    })
    # Exporters read OTEL_EXPORTER_OTLP_ENDPOINT (default http://localhost:4318).
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    interval_ms = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "5000"))
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=interval_ms)],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    # Every Python log record is exported with the active trace/span id, and the
    # console format gains trace_id/span_id so plain logs can be matched to traces.
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
    for handler in logging.getLogger().handlers:
        if not isinstance(handler, LoggingHandler):
            handler.addFilter(_TraceContextFilter())
            handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s "
                "[trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(message)s"
            ))

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,assets/.*", exclude_spans=["receive", "send"])
    HTTPXClientInstrumentor().instrument()
    _state.update(
        enabled=True,
        instruments=_Instruments(),
        providers=(tracer_provider, meter_provider, logger_provider),
    )
    logger.info("otel_enabled service=%s endpoint=%s", resource.attributes["service.name"],
                os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"))
    return True


class _TraceContextFilter(logging.Filter):
    """Add the active trace/span id to every console log line."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = trace.get_current_span().get_span_context()
        record.otelTraceID = format(context.trace_id, "032x") if context.is_valid else "0"
        record.otelSpanID = format(context.span_id, "016x") if context.is_valid else "0"
        return True


def shutdown_observability() -> None:
    """Flush buffered telemetry on application shutdown."""
    for provider in _state.get("providers", ()):
        try:
            provider.shutdown()
        except Exception:  # pragma: no cover - best effort during shutdown
            pass


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Start a child span (and time the stage) when telemetry is enabled."""
    if not telemetry_enabled():
        yield None
        return
    import time

    started = time.perf_counter()
    tracer = trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span(name, attributes=_clean(attributes)) as current:
        try:
            yield current
        finally:
            _state["instruments"].stage_duration.record(
                time.perf_counter() - started, {"stage": name}
            )


def set_attributes(**attributes: Any) -> None:
    if telemetry_enabled():
        trace.get_current_span().set_attributes(_clean(attributes))


def mark_error(exc: BaseException, message: str | None = None) -> None:
    if telemetry_enabled():
        current = trace.get_current_span()
        current.record_exception(exc)
        current.set_status(Status(StatusCode.ERROR, message or type(exc).__name__))


def record_request(workflow: str, status_code: int, seconds: float) -> None:
    """Count every analysis HTTP request by workflow and status (called by middleware)."""
    if not telemetry_enabled():
        return
    inst = _state["instruments"]
    outcome = "success" if status_code < 400 else ("client_error" if status_code < 500 else "server_error")
    labels = {"workflow": workflow, "http_status": str(status_code), "outcome": outcome}
    inst.requests.add(1, labels)
    inst.duration.record(seconds, {"workflow": workflow, "outcome": outcome})


def record_result(workflow: str, mode: str, analysis_status: str,
                  catchment_ha: float | None, runoff_m3: float | None, **extra: Any) -> None:
    """Attach the scientific result to the current span and the result histograms."""
    if not telemetry_enabled():
        return
    set_attributes(**{
        "pond.workflow": workflow, "pond.selection_mode": mode,
        "pond.analysis_status": analysis_status,
        "pond.catchment_ha": catchment_ha, "pond.runoff_m3": runoff_m3,
        **{f"pond.{key}": value for key, value in extra.items()},
    })
    inst = _state["instruments"]
    labels = {"workflow": workflow, "analysis_status": analysis_status}
    if catchment_ha is not None:
        inst.catchment_area.record(catchment_ha, labels)
    if runoff_m3 is not None:
        inst.runoff_volume.record(runoff_m3, labels)


def record_source_failure(source: str, reason: str) -> None:
    if telemetry_enabled():
        _state["instruments"].source_failures.add(1, {"source": source, "reason": reason[:60]})


def _clean(attributes: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in attributes.items()
            if isinstance(value, (str, bool, int, float))}

"""OpenTelemetry instrumentation emits pipeline spans and metrics when enabled."""

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import observability
from services.contour_analyzer import analyze_contour_file
from tests.test_contour_analyzer import synthetic_kml


@pytest.fixture
def telemetry(monkeypatch):
    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(observability.trace, "get_tracer",
                        lambda *args, **kwargs: tracer_provider.get_tracer("test"))
    monkeypatch.setattr(observability.metrics, "get_meter",
                        lambda *args, **kwargs: meter_provider.get_meter("test"))
    monkeypatch.setitem(observability._state, "enabled", True)
    monkeypatch.setitem(observability._state, "instruments", observability._Instruments())
    yield exporter, reader
    monkeypatch.setitem(observability._state, "enabled", False)


def test_disabled_helpers_are_no_ops():
    assert not observability.telemetry_enabled()
    with observability.span("anything", value=1) as current:
        assert current is None
    observability.record_request("contour", 200, 0.1)
    observability.record_source_failure("rainfall", "timeout")


def test_contour_pipeline_emits_stage_spans_and_metrics(telemetry):
    exporter, reader = telemetry
    result = analyze_contour_file(synthetic_kml(), "terrain.kml")
    observability.record_request("contour", 200, 1.5)

    names = [item.name for item in exporter.get_finished_spans()]
    for stage in (
        "contour.parse_kml",
        "terrain.harmonic_interpolation",
        "terrain.priority_flood",
        "terrain.resolve_flats_d8",
        "terrain.flow_accumulation",
        "terrain.rank_candidates",
        "terrain.delineate_catchment",
    ):
        assert stage in names
    catchment = next(s for s in exporter.get_finished_spans() if s.name == "terrain.delineate_catchment")
    assert catchment.attributes["catchment_ha"] == pytest.approx(result["catchment"]["area_sqm"] / 10_000, rel=1e-3)

    metric_names = {
        metric.name
        for resource in reader.get_metrics_data().resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }
    assert {"pond.pipeline.stage.duration", "pond.analysis.requests", "pond.analysis.duration"} <= metric_names

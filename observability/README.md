# OpenTelemetry (Lab 8)

The backend emits **traces, metrics and logs** over OTLP/HTTP when `OTEL_ENABLED=true`
(see `backend/observability.py`). Without that flag, or without the OpenTelemetry
packages, the app runs exactly as before.

Pipeline: `FastAPI app --OTLP/HTTP:4318--> OpenTelemetry Collector`
→ traces to **Jaeger** (UI :16686), metrics to a **Prometheus** exporter (:8889, scraped by Prometheus UI :9090),
logs to a JSON file (`logs.jsonl`) and the collector console.

```sh
jaeger-all-in-one --collector.otlp.grpc.host-port=127.0.0.1:14317 --collector.otlp.http.host-port=127.0.0.1:14318
otelcol-contrib --config observability/collector.yaml
prometheus --config.file=observability/prometheus.yml
python observability/run_app.py --port 8001 --offline-fixtures   # external tiles/rainfall replaced by local fixtures
python observability/run_app.py --port 8002                      # real network adapters
```

Versions used: OpenTelemetry Python SDK 1.45.1 (instrumentation 0.66b1), Collector contrib 0.111.0,
Jaeger 1.62.0, Prometheus 2.53.2. Adjust the `file/logs` path in `collector.yaml` for your machine.

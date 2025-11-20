import importlib
import importlib.util
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from prometheus_client import Counter, Gauge, Histogram


INGESTION_COUNTER = Counter(
    "gps_ingestions_total",
    "Total de posiciones ingresadas por dispositivo.",
    ["device_id"],
)

ALERT_DELIVERY_COUNTER = Counter(
    "gps_alert_notifications_total",
    "Entregas e intentos de entrega de alertas a contactos.",
    ["channel", "status"],
)

API_LATENCY = Histogram(
    "gps_api_latency_seconds",
    "Latencia por handler FastAPI.",
    ["method", "path", "status_code"],
    buckets=(
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
    ),
)

DEVICE_LAST_SEEN = Gauge(
    "gps_device_last_seen_epoch",
    "Marca de tiempo UNIX del último heartbeat por dispositivo.",
    ["device_id"],
)

DEVICE_ONLINE = Gauge(
    "gps_device_online",
    "Estado de conectividad del dispositivo (1=online, 0=offline).",
    ["device_id"],
)


class Observability:
    """Configura tracing, métricas personalizadas y perfiles opcionales."""

    def __init__(self, app: FastAPI):
        self.app = app
        self.profiler: Any = None
        self.output_path: Path | None = None
        self._attach_latency_middleware()
        self._configure_tracing()
        self._maybe_enable_profiler()

    def _configure_tracing(self) -> None:
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if not endpoint:
            return

        if importlib.util.find_spec("opentelemetry.sdk.trace") is None:
            return

        trace_mod = importlib.import_module("opentelemetry.trace")
        exporter_mod = importlib.import_module(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter"
        )
        resources_mod = importlib.import_module("opentelemetry.sdk.resources")
        sdk_trace = importlib.import_module("opentelemetry.sdk.trace")
        sdk_export = importlib.import_module("opentelemetry.sdk.trace.export")
        requests_inst = importlib.import_module("opentelemetry.instrumentation.requests")
        fastapi_inst = importlib.import_module("opentelemetry.instrumentation.fastapi")

        resource = resources_mod.Resource.create(
            {
                "service.name": os.getenv("OTEL_SERVICE_NAME", "gps-tracker-api"),
                "service.namespace": os.getenv("OTEL_SERVICE_NAMESPACE", "gps"),
                "service.instance.id": os.getenv("HOSTNAME", "local"),
            }
        )

        provider = sdk_trace.TracerProvider(resource=resource)
        span_exporter = exporter_mod.OTLPSpanExporter(
            endpoint=endpoint,
            timeout=int(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "10")),
        )
        provider.add_span_processor(sdk_export.BatchSpanProcessor(span_exporter))
        trace_mod.set_tracer_provider(provider)
        requests_inst.RequestsInstrumentor().instrument()
        fastapi_inst.FastAPIInstrumentor.instrument_app(
            self.app, tracer_provider=provider
        )

    def _attach_latency_middleware(self) -> None:
        @self.app.middleware("http")
        async def record_latency(request: Request, call_next):  # type: ignore[arg-type]
            start = time.perf_counter()
            response = await call_next(request)
            elapsed = time.perf_counter() - start

            route_template = request.url.path
            route = request.scope.get("route")
            if route and getattr(route, "path", None):
                route_template = route.path

            API_LATENCY.labels(
                method=request.method,
                path=route_template,
                status_code=str(response.status_code),
            ).observe(elapsed)
            return response

    def _maybe_enable_profiler(self) -> None:
        if os.getenv("ENABLE_PROFILING", "").lower() not in {"1", "true", "yes"}:
            return

        if importlib.util.find_spec("pyinstrument") is None:
            return

        profiler_module = importlib.import_module("pyinstrument")
        profiler_cls = getattr(profiler_module, "Profiler", None)
        if profiler_cls is None:
            return

        output = Path(os.getenv("PROFILE_OUTPUT", "./profile.txt"))
        output.parent.mkdir(parents=True, exist_ok=True)
        self.profiler = profiler_cls(async_mode="enabled", interval=0.001)
        self.profiler.start()
        self.output_path = output

    def stop_profiler(self) -> Path | None:
        if not self.profiler or not self.output_path:
            return None
        self.profiler.stop()
        profile_text = self.profiler.output_text(unicode=True, color=False)
        self.output_path.write_text(profile_text, encoding="utf-8")
        return self.output_path


def record_ingestion(device_id: str) -> None:
    """Incrementa las métricas de ingestión y latencia de heartbeat."""

    INGESTION_COUNTER.labels(device_id=device_id).inc()
    DEVICE_LAST_SEEN.labels(device_id=device_id).set_to_current_time()
    DEVICE_ONLINE.labels(device_id=device_id).set(1)


def record_alert_delivery(channel: str, status: str = "delivered") -> None:
    """Cuenta entregas de alertas por canal (email/webhook/push)."""

    ALERT_DELIVERY_COUNTER.labels(channel=channel, status=status).inc()


def mark_device_offline(device_id: str) -> None:
    """Permite marcar dispositivos como offline en sondeos externos."""

    DEVICE_ONLINE.labels(device_id=device_id).set(0)

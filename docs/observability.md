# Observabilidad, alertas y soporte

## Métricas clave y validaciones rápidas

- **Ingestiones/minuto**: `sum(rate(gps_ingestions_total[1m]))`.
  - Detecta caídas de flujo de posiciones o retardo de colas.
- **Latencia API**: `histogram_quantile(0.95, rate(gps_api_latency_seconds_bucket[5m]))`.
  - Útil para SLOs de 500 ms p95 y correlación con trazas.
- **Entrega de alertas**: `increase(gps_alert_notifications_total[5m])` filtrado por `status` (`delivered/failed`).
  - El pipeline que envíe emails/webhooks debe invocar `record_alert_delivery` con el estado real.
- **Uptime de dispositivos**:
  - Último heartbeat: `gps_device_last_seen_epoch` por `device_id`.
  - Estado online/offline: `gps_device_online{device_id="<id>"}`; alert rule usa 5 minutos de silencio.
- **Scrape y dashboards**:
  - `/metrics` se expone en la API y Prometheus lo recoge cada 15s (`deployments/prometheus/prometheus.yml` -> job `api`).
  - Verifica `http://localhost:9090/targets` para confirmar estado `UP` y `http://localhost:3000` carga el dashboard `gps-observability` sin datasources faltantes (provisión apunta a la carpeta `deployments/grafana/dashboards`).

## Dashboards y alertas

- Grafana carga automáticamente el dashboard `deployments/grafana/dashboards/gps-observability.json` (provisión en `/etc/grafana/provisioning`).
  - Incluye ingestiones/min, latencia p95, alertas entregadas/errores y uptime por dispositivo.
- Prometheus aplica reglas en `deployments/prometheus/alerts.yml` y envía a Alertmanager (`docker-compose` expone `:9093`).
  - Páginas: latencia p95 > 450 ms durante 5m o ingestiones < 0.5/min por 5m.
  - Tickets: fallos de entrega de alertas o dispositivos sin heartbeat > 5m.
- Alertmanager reenvía a webhook (`/alerts/webhook` en el gateway) y a `oncall@example.com`; ajusta receptores según tu sistema de guardias.

## Tracing distribuido y perfiles

- Exporta trazas OTLP configurando `OTEL_EXPORTER_OTLP_ENDPOINT` (por ejemplo `http://otel-collector:4318/v1/traces`).
  - Variables opcionales: `OTEL_SERVICE_NAME`, `OTEL_SERVICE_NAMESPACE`, `OTEL_SERVICE_VERSION`, `OTEL_DEPLOYMENT_ENVIRONMENT`, `OTEL_EXPORTER_OTLP_TIMEOUT`.
  - Los spans incluyen `service.name=gps-tracker-api`, `service.namespace=gps`, `service.version` (default `dev`) y `deployment.environment` (default `local`).
- Habilita perfiles de rendimiento activando `ENABLE_PROFILING=1` (genera `profile.txt` en el contenedor, configurable con `PROFILE_OUTPUT`).
- El tracing instrumenta FastAPI y las llamadas `requests`/`httpx`, permitiendo seguir la latencia end-to-end.

## Validación de alertas (datos simulados)

- Ejecuta tests sintéticos de reglas con promtool: `docker run --rm -v $(pwd)/deployments/prometheus:/etc/prometheus prom/prometheus:v2.53.2 promtool test rules /etc/prometheus/alerts.test.yml`.
  - El fixture `deployments/prometheus/alerts.test.yml` fuerza picos de p95, caídas de ingestión y dispositivos sin heartbeat para validar Alertmanager.
- Para verlas encendidas en Alertmanager local, sube el stack (`docker-compose up prometheus alertmanager api`) y consulta `http://localhost:9093`.

## Runbooks por alerta

### Alerta de latencia p95 alta
- Umbral: p95 > 450 ms sostenidos por 5m (se agrupa por `path`).
- Pasos:
  1. Revisar panel "Latencia API p95" en Grafana por ruta y comparar con trazas filtrando `deployment.environment`.
  2. Validar conexiones a DB/Redis y recientes despliegues; si hay regresión, aplicar rollback o escalar replicas.
  3. Capturar perfiles (`ENABLE_PROFILING=1`) durante 2-3 minutos y adjuntar al ticket.

### Caída de ingestiones
- Umbral: `sum(rate(gps_ingestions_total[5m])) < 0.5` durante 5m.
- Pasos:
  1. Confirmar en Grafana que los paneles de ingestiones están planos; revisar gateway `/health` y logs de API.
  2. Validar Redis/colas y certificados de dispositivos; reintentar con `scripts/synthetic_checks.py` para varios `X-Region`.
  3. Si afecta a un subconjunto, contactar clientes afectados; documentar reinicios o cortes de red.

### Fallos en entrega de alertas
- Umbral: `increase(gps_alert_notifications_total{status="failed"}[5m]) > 0` (ticket).
- Pasos:
  1. Revisar panel de alertas entregadas/errores por `status` y logs del servicio de notificaciones.
  2. Forzar un reintento manual o cambiar de canal (SMS/push). Si es masivo, pausar el pipeline y redirigir a webhook de fallback.
  3. Registrar causa raíz y contactos fallidos en el postmortem.

### Dispositivo sin heartbeat
- Umbral: sin actualización de `gps_device_last_seen_epoch` > 5m (evalúa ventanas de 5m y espera 2m antes de alertar).
- Pasos:
  1. Revisar panel "Uptime por dispositivo"; si sólo afecta a un equipo, validar token/certificados del dispositivo.
  2. Consultar `/fleet/live?device_id=<id>` y verificar si hay latencia o colas atrasadas.
  3. Escalar a soporte de campo si persiste >15m y documentar acciones en el ticket.

## Playbooks de incidentes (on-call)

1. **Alerta de latencia p95 alta**
   - Revisa el dashboard de latencia y el panel de trazas en tu colector (filtra por endpoint lento).
   - Verifica conexiones a DB/Redis; si hay contención, escala replicas de API o optimiza consultas.
   - Si hay despliegue reciente, realiza rollback o aplica mitigaciones (rate-limit, cachear respuestas).
2. **Caída de ingestiones o dispositivos offline**
   - Confirma en Prometheus si todos los `device_id` muestran `gps_device_online=0` o es un subconjunto.
   - Comprueba gateway/API (`/health`) y colas/Redis; valida certificados o tokens de dispositivos.
   - Coordina con soporte para contactar clientes afectados; documenta en el ticket raíz.
3. **Errores de entrega de alertas**
   - Inspecciona incrementos en `gps_alert_notifications_total{status="failed"}` y los logs del pipeline de notificaciones.
   - Reintenta manualmente con el webhook de fallback o cambia el canal (email→SMS/push).
   - Comunica en el canal de incidentes y registra postmortem con causas y acciones.

## Runbooks de soporte

- **Alta de dispositivo**: usa `/devices/register` y confirma `gps_device_last_seen_epoch` después de la primera ingesta.
- **Verificación de cliente**: consulta `/fleet/live?username=<user>` y valida que los widgets de Grafana muestran ingestas > 0.
- **Mantenimiento preventivo**: programa sondeos sintéticos (`scripts/synthetic_checks.py`) desde múltiples regiones para detectar TLS/latencia.
- **Rotación de claves/alertas**: al actualizar tokens o contactos, emite un `record_alert_delivery(channel, status="failed")` si detectas rechazos para facilitar troubleshooting.

## Tests de humo y sintéticos

- `pytest tests/test_synthetic_probes.py` valida health e ingestión simulada desde varias regiones lógicas.
- `scripts/synthetic_checks.py` permite lanzar probes programados con `SYNTHETIC_REGIONS`, `SYNTHETIC_BASE_URL` y `SYNTHETIC_DEVICE_TOKEN`.

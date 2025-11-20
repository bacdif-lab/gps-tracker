# Operación, CI/CD y observabilidad

## CI
GitHub Actions ejecuta lint, tests y builds de imágenes:
- **Lint**: `flake8` placeholder (se puede ampliar con ruff/mypy).
- **Tests**: `pytest` con dependencias en `requirements-dev.txt`.
- **Build web**: construcción de la imagen del frontend (`Dockerfile.frontend`).
- **Build móvil**: usa secrets de firma (`APP_STORE_CONNECT_API_KEY`, `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`) y ejecuta `eas build --profile production` (Expo) o `fastlane ios beta` / `fastlane android beta` para generar IPA/AAB listos para TestFlight/Play Store Internal Testing.

## CD
El workflow `cd.yml` despliega a los entornos declarados:
- **Staging**: publicación de imágenes y despliegue automático cuando se hace push a `main`.
- **Producción**: gating manual (`environment: production`) y reutilización de artefactos.
Ambos jobs son hooks listos para reemplazar con comandos de infraestructura (Helm, ECS, etc.).

## Monitorización
- `prometheus_fastapi_instrumentator` expone `/metrics` en la API.
- `deployments/prometheus/prometheus.yml` configura el scrape de la API y carga reglas en `deployments/prometheus/alerts.yml`.
- Grafana (puerto 3000) usa provisión automática (`deployments/grafana/provisioning`) y dashboards en `deployments/grafana/dashboards`.
- Alertmanager (puerto 9093) reenvía a webhook/email según `deployments/alertmanager/alertmanager.yml`.
- Métricas clave, alertas y playbooks documentados en `docs/observability.md`.

## Logging centralizado
- La API y el gateway escriben logs en stdout en formato plano; configúralos para JSON si se envían a ELK/CloudWatch.
- Para CloudWatch, agrega el agente (`awslogs`) en los contenedores o un sidecar de Fluent Bit.
- Para ELK/Loki, conecta un shipper (Filebeat/Fluent Bit) leyendo de los sockets Docker y enviando a Logstash/OpenSearch.

## Datos seed y desarrollo local
- `docker-compose up --build` levanta la pila con PostgreSQL+PostGIS, Redis, API, frontend, gateway y observabilidad básica.
- El contenedor `seed` carga un usuario `demo` y posiciones de prueba tras crearse la base de datos.
- Los certificados TLS de desarrollo deben ubicarse en `deployments/gateway/certs` (`local.crt` y `local.key`).

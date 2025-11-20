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
- `deployments/prometheus/prometheus.yml` configura el scrape de la API.
- Grafana (puerto 3000) puede apuntar al datasource Prometheus (`http://prometheus:9090`).
- Añade dashboards de API y base de datos; importa reglas de alerting según tus SLOs.

## Logging centralizado
- La API y el gateway escriben logs en stdout en formato plano; configúralos para JSON si se envían a ELK/CloudWatch.
- Para CloudWatch, agrega el agente (`awslogs`) en los contenedores o un sidecar de Fluent Bit.
- Para ELK/Loki, conecta un shipper (Filebeat/Fluent Bit) leyendo de los sockets Docker y enviando a Logstash/OpenSearch.

## Datos seed y desarrollo local
- `docker-compose up --build` levanta la pila con PostgreSQL+PostGIS, Redis, API, frontend, gateway y observabilidad básica.
- El contenedor `seed` carga un usuario `demo` y posiciones de prueba tras crearse la base de datos.
- Los certificados TLS de desarrollo deben ubicarse en `deployments/gateway/certs` (`local.crt` y `local.key`).

## Despliegue y operaciones
### Staging
- Empaqueta imágenes con el tag `staging` y publícalas en el registry configurado.
- Despliega con Docker Compose (`docker-compose -f docker-compose.yml -f deployments/compose.staging.yml up -d`) o con Helm apuntando a los valores de staging.
- Semillas: habilita el contenedor `seed` únicamente en staging para cargar datos demo y validar dashboards.
- TLS: certificados emitidos por ACME/Let’s Encrypt o secretos inyectados en `deployments/gateway/certs`.

### Producción
- Imágenes firmadas y versionadas (`api:vX.Y.Z`, `frontend:vX.Y.Z`).
- Infraestructura con volúmenes persistentes (PostgreSQL/Redis gestionados o StatefulSets) y replicaset mínimo de 2 pods para API/frontend detrás de un ingress/gateway.
- Health checks y autoscaling (HPA) basados en latencia/p95 y consumo de CPU/Memoria.
- Bloquear el contenedor `seed` y cualquier usuario demo; aplicar migraciones antes de subir tráfico.

### Backup y restore de base de datos
- **Backup completo**: `pg_dump -Fc "$DATABASE_URL" > backups/gps-$(date +%F).dump` ejecutado desde un job diario; almacenar en S3 con versión y retención.
- **Restore**: `pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL" backups/gps-YYYY-MM-DD.dump`; realizar en una base vacía o en instancia temporal para verificaciones.
- **Point-in-time**: habilitar WAL archiving en PostgreSQL gestionado para recuperar hasta el último segmento disponible.

### Rotación de secretos
- Gestionar secretos en un vault (AWS Secrets Manager, GCP SM, Vault) y montarlos como variables/archivos en los contenedores.
- Rotar `JWT_SECRET`, claves de DB y tokens de mapas con doble publicación: 1) agregar el secreto nuevo y reiniciar los pods, 2) revocar el antiguo y reiniciar nuevamente.
- Automatizar rotaciones con pipelines programados y alertas de expiración (por ejemplo, 7 días antes de caducar certificados TLS o claves FCM/APNs).

### Playbooks rápidos
- **Reinicio controlado de API**: drenar tráfico en el gateway/ingress, esperar a que no haya requests en curso y reiniciar los pods; validar `/health` antes de volver a enrutar.
- **Failover de DB**: apuntar `DATABASE_URL` al replica/promote seleccionado, vaciar conexiones viejas y recalentar caches en Redis (p. ej., precargar vehículos activos).
- **Recuperación de Redis**: si se pierde la cola, reprocesar eventos desde una tabla de staging en PostgreSQL y volver a publicar en Redis.

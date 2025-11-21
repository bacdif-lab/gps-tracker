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
- Rotar `JWT_SECRET`, claves de DB, tokens de mapas y credenciales FCM/APNs con doble publicación: 1) agregar el secreto nuevo y reiniciar los pods, 2) revocar el antiguo y reiniciar nuevamente.
- Durante la ventana de rotación, valida que la API responde `200` en `/health`, que el gateway sigue sirviendo al frontend y que los workers de notificaciones continúan entregando mensajes (FCM/APNs) antes de revocar la clave antigua.
- En rotaciones de DB, usa cuentas con password temporal y prueba conexiones de lectura/escritura antes de forzar el corte; para JWT verifica que sesiones activas se renuevan con el nuevo secreto.

### Expiraciones y alertas preventivas
- Configura alertas que avisen al menos 7 días antes de vencer certificados TLS, credenciales de mapas y claves FCM/APNs; usa jobs programados o reglas en Alertmanager (webhook/email).
- Documenta las fechas de expiración en el vault y revisa semanalmente las claves cercanas a vencimiento; automatiza la creación de tickets para rotaciones pendientes.
- Integra monitoreo que detecte fallos de publicación dual (p. ej., entregas FCM/APNs que caen a cero durante la rotación) para disparar rollback temprano.

### Semillas y usuarios demo
- Bloquear el contenedor `seed` en producción; únicamente habilitarlo en staging para validar dashboards y datos de prueba.
- Deshabilitar o eliminar usuarios demo antes de exponer tráfico real; auditar accesos en cada despliegue mediante `AuditLog` y alertas por inicio de sesión de cuentas no productivas.

### Controles web (CORS/CSRF, rate limiting, MFA)
- Define `CORS_ALLOW_ORIGINS` con el dominio del gateway/frontend y evita comodines en producción; mantén `X-CSRF-Token` y `X-MFA-Code` en la lista de headers permitidos.
- El rate limiting de API (`RATE_LIMIT_PER_MINUTE`) debe ajustarse según la carga esperada y medirse con métricas de rechazo (`HTTP 429`).
- Requiere MFA para administradores y operadores de paneles; verifica enrolamiento y fallback seguro antes de cada ventana de cambios de credenciales.
- Automatizar rotaciones con pipelines programados y alertas de expiración (por ejemplo, 7 días antes de caducar certificados TLS o claves FCM/APNs).

### Playbooks rápidos
- **Reinicio controlado de API**: drenar tráfico en el gateway/ingress, esperar a que no haya requests en curso y reiniciar los pods; validar `/health` antes de volver a enrutar.
- **Failover de DB**: apuntar `DATABASE_URL` al replica/promote seleccionado, vaciar conexiones viejas y recalentar caches en Redis (p. ej., precargar vehículos activos).
- **Recuperación de Redis**: si se pierde la cola, reprocesar eventos desde una tabla de staging en PostgreSQL y volver a publicar en Redis.

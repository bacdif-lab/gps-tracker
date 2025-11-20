# GPS Tracker

Stack de referencia para rastreo GPS con FastAPI, PostgreSQL/PostGIS y frontend estático detrás de un gateway Nginx.

## Integraciones clave
- Tiles, geocodificación inversa y ruteo vía `/api/maps/*` usando Mapbox u OSM según `MAP_PROVIDER`.
- Notificaciones (correo/SMS/push) encoladas en Redis mediante `/api/notifications/queue` y worker asíncrono.
- Pasarelas de pago (Stripe o MercadoPago) con creación de sesiones y webhook HMAC en `/api/payments/*`.
- Ingesta de protocolos GPS populares (Teltonika/Queclink/Concox) vía `/api/ingest/protocol` o servidor TCP con adaptadores.

## Ejecución local
1. Genera certificados locales en `deployments/gateway/certs` (`local.crt` y `local.key`).
2. Levanta los servicios: `docker-compose up --build`.
3. La API quedará en `https://localhost:8443/api`, el frontend en `https://localhost:8443/` y las métricas en `http://localhost:9090` (Prometheus) / `http://localhost:3000` (Grafana).
4. Usuarios y posiciones de demo se crean automáticamente mediante el contenedor `seed`.

## Variables principales
- `DATABASE_URL`: conexión a PostgreSQL/PostGIS (por defecto `postgresql+psycopg2://gps:gps@db:5432/gps`).
- `REDIS_URL`: endpoint de Redis para caché/colas.
- `MAP_PROVIDER`: selecciona proveedor de mapas (Mapbox/OSM) para futuras integraciones en frontend/API.
- `AWS_*` o credenciales equivalentes para S3 si se habilita almacenamiento de archivos.

## CI/CD y observabilidad
- Workflows de GitHub Actions en `.github/workflows` ejecutan lint, tests y builds de imágenes; los despliegues a staging/producción son hooks configurables.
- Prometheus/Grafana se incluyen en `docker-compose.yml` y la API expone `/metrics` instrumentado.

Consulta `docs/architecture.md` para el diagrama de topología y `docs/operations.md` para detalles operativos.

## App móvil

La guía `docs/mobile_app.md` resume stack, seguridad (JWT/OAuth2 + refresh), pantallas clave (mapa en vivo, lista/detalle de vehículos, replay histórico) y lineamientos para alertas push, modo offline y builds hacia TestFlight/Play Store.

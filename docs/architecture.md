# Topología y dependencias

## Visión general

- **Gateway HTTPS (Nginx)**: termina TLS y enruta `/api/*` hacia la API FastAPI, `/metrics` para observabilidad y el resto hacia el frontend estático.
- **API (FastAPI)**: expone endpoints REST y `/metrics` instrumentado con Prometheus. Se ejecuta detrás del gateway.
- **Base de datos (PostgreSQL + PostGIS)**: almacena usuarios, dispositivos y posiciones con soporte geoespacial para futuras consultas.
- **Redis (colas/caché)**: disponible para colas de procesado o caché de sesiones.
- **Servicio de mapas (Mapbox/OSM)**: la clave `MAP_PROVIDER` permite seleccionar proveedor y consumir tiles externos.
- **Almacenamiento de archivos (S3 o equivalente)**: pensado para adjuntar exports, respaldos o trazas; se conecta mediante credenciales de entorno.
- **Observabilidad**: Prometheus scrapea la API y Grafana visualiza dashboards. Logs estructurados se envían al gateway o a un shipper hacia ELK/CloudWatch.

```
+-------------+      +-------------+      +-----------------+
|  Frontend   +----->+  Gateway    +----->+   API FastAPI   |
| (Nginx)     | 443  | (HTTPS/TLS) | 80   |  /metrics, /api |
+-------------+      +------+------+      +---------+-------+
                             |                       |
                             |                       v
                             |               PostgreSQL + PostGIS
                             |                       |
                             |                       v
                             |                     Redis
                             |
                             v
                      Prometheus/Grafana
```

## Flujo de red
1. El cliente llega por HTTPS al gateway.
2. El gateway reenvía peticiones `/api` a `api:8000` y sirve el frontend estático.
3. `/metrics` queda disponible sólo a Prometheus.
4. La API usa `DATABASE_URL` para conectar a PostgreSQL/PostGIS y `REDIS_URL` para colas/caché.
5. Requests que usen mapas se sirven desde Mapbox u OSM mediante las claves configuradas.

## Seguridad
- TLS obligatorio desde el gateway; renovar certificados con ACME/Let’s Encrypt en entornos reales.
- Variables de entorno para credenciales (DB, S3, Mapbox).
- Tokens JWT con expiración y hashing bcrypt para usuarios.
- PostGIS habilitado desde `deployments/initdb` para operaciones geoespaciales.

## Escalabilidad
- API y frontend son stateless -> escalar horizontalmente tras el gateway.
- Redis permite manejar colas de ingestión y cacheo de tokens.
- Base de datos y almacenamiento de archivos se escalan mediante réplicas gestionadas o servicios del cloud provider.

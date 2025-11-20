# Manual de usuario

Este manual resume las acciones principales para administradores y clientes finales, junto con preguntas frecuentes y pasos de troubleshooting.

## Roles y accesos
- **Administradores**: crean usuarios, gestionan dispositivos/vehículos, configuran alertas y revisan reportes.
- **Clientes**: consultan vehículos asignados, revisan posiciones en vivo, generan exportes y reciben notificaciones.

## Autenticación
1. Accede a `https://<dominio>/` y selecciona **Iniciar sesión**.
2. Introduce correo y contraseña; el sistema entrega un token JWT con expiración.
3. Para seguridad adicional, habilita MFA si está disponible; en móviles, el token se renueva en segundo plano.

## Flujos para administradores
- **Alta de vehículos/dispositivos**: 
  1. Navega a **Inventario > Vehículos** y presiona **Agregar**.
  2. Ingresa VIN/alias, asigna un dispositivo y define geocercas opcionales.
  3. Guarda y verifica que aparezca la última posición; si no, revisa conectividad del dispositivo.
- **Gestión de usuarios**: crea usuarios con rol Admin/Operador/Cliente y asigna vehículos o tenants según política.
- **Alertas**: 
  - Configura reglas (exceso de velocidad, salida de geocerca, desconexión) y define severidades.
  - Asigna canales: push, email o webhooks hacia sistemas externos.
- **Reportes y exportes**: genera CSV/GeoJSON desde **Reportes**; los archivos se almacenan temporalmente en S3/MinIO.

## Flujos para clientes
- **Mapa en vivo**: filtra por estado/etiquetas, activa clustering y selecciona un vehículo para ver detalle.
- **Histórico/replay**: elige rango de fechas y reproduce la ruta; ajusta velocidad de reproducción y puntos clave.
- **Notificaciones**: habilita permisos de push en el navegador/móvil; las alertas llegan a los tópicos asignados.
- **Soporte**: usa el botón **Enviar feedback** para adjuntar capturas y logs (si están habilitados en el frontend).

## FAQ de dispositivos
- **¿Qué protocolos soporta la ingesta?** HTTP(S) y WebSocket con payload JSON; se pueden agregar parsers adicionales en la API.
- **¿Cómo registro un dispositivo nuevo?** Crea el dispositivo en **Inventario**, asocia el IMEI/ID y genera un token para la app/firmware.
- **¿Qué hacer si un dispositivo deja de reportar?** Verifica alimentación y cobertura; revisa métricas de ingestión y colas en Redis. Si persiste, rota el token del dispositivo.
- **¿Se pueden cargar datos históricos?** Sí, mediante importación CSV/GeoJSON a través de la API de administración.

## Troubleshooting
- **HTTP 401/403**: expira el token; vuelve a iniciar sesión o solicita que un admin regenere credenciales.
- **Mapa vacío**: revisa `MAPBOX_TOKEN` o proveedor OSM; valida que el endpoint `/api/positions` devuelva datos y que no haya filtros activos.
- **Retraso en alertas**: comprueba la cola en Redis y el worker de alertas; si hay backlog, escala réplicas o purga mensajes corruptos.
- **Backup/restore fallido**: verifica permisos de escritura en el bucket S3 y que la versión de `pg_dump`/`pg_restore` coincida con la del servidor.
- **Notificaciones push no llegan**: revisa certificados/APNs o claves FCM, y confirma que el usuario esté suscrito al tópico correcto.

## Buenas prácticas
- Habilita MFA para administradores y rotación periódica de contraseñas.
- Usa etiquetas y geocercas para organizar flotas y acelerar búsquedas.
- Define ventanas de mantenimiento para despliegues y comunica a los clientes posibles interrupciones.

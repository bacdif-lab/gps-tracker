# Aplicación móvil: lineamientos de arquitectura y entrega

## Objetivo
Habilitar un cliente móvil (Flutter o React Native) que consuma la API de GPS Tracker con autenticación segura, mapas en vivo, lista/detalle de vehículos, replay histórico y alertas push, optimizando consumo de datos/batería y soportando modo offline.

## Stack sugerido
- **Cliente**: Flutter (Riverpod/Bloc) o React Native (Expo Router + React Query).
- **Auth**: OAuth2 con PKCE contra `/api/auth/authorize`/`/api/auth/token` o JWT + refresh en `/api/auth/login` y `/api/auth/refresh`.
- **Networking**: `dio`/`http` + interceptors (Flutter) o `axios`/`fetch` con `react-query` (RN) para caché, reintentos y políticas de stale-while-revalidate.
- **Mapas**: `mapbox_gl` o `react-native-mapbox-gl` con tiles vectoriales para menor consumo; fallback a OSM en entornos sin clave.
- **Estado y almacenamiento**: `hive`/`sqflite` (Flutter) o `react-native-mmkv`/`AsyncStorage` (RN) para caché de sesiones, vehículos recientes y trazas offline.

## Autenticación segura
1. **Login**: formulario captura credenciales y solicita token de acceso + refresh.
2. **Almacenamiento**: guardar refresh token en storage seguro (`flutter_secure_storage` o Keychain/Keystore) y access token en memoria/short-term storage.
3. **Rotación**: interceptors renuevan access token ante 401 usando `/api/auth/refresh`; si falla, cerrar sesión y limpiar caché.
4. **Protección**: activar App Transport Security (iOS) / Network Security Config (Android) solo para hosts TLS (`https://localhost:8443` en desarrollo con certificados del repo).
5. **Deep links**: configurar `app://auth/callback` para PKCE y asociar universal links / Android App Links.

## Pantallas clave
- **Mapa en vivo**: mapa centrado en bounding box de vehículos, clustering y filtrado por estado. Polling o WebSocket opcional (`/api/ws/positions`) con backoff exponencial.
- **Lista de vehículos**: vista con búsqueda y filtros (por estado, geocerca, conductor). Muestra último fix, velocidad y batería.
- **Detalle**: ficha del vehículo con eventos recientes (ignición, alertas, geocercas) consultando `/api/vehicles/{id}/events?limit=20`.
- **Replay histórico**: selector de rango temporal que consulta `/api/vehicles/{id}/track?from=..&to=..` y reproduce en el mapa con control de velocidad.
- **Alertas y push**: preferencias por tipo (exceso de velocidad, desconexión, batería baja). Suscripción push con FCM (Android/iOS) y APNs; el backend envía mensajes a tópicos `{tenant}/alerts`.

## Optimización de datos y batería
- Reducir intervalos de polling en background; usar WebSocket cuando haya conectividad estable.
- Habilitar **delta updates**: endpoints devuelven `last_position_id` para que el cliente sólo pida cambios desde ese punto.
- Limitar frecuencia de re-render en el mapa (agrupar actualizaciones cada 2-5s) y usar tiles vectoriales.
- Comprimir payloads (`Accept-Encoding: gzip/br`) y paginar listas (`page/limit`).
- Guardar últimas posiciones en caché local para render inmediato y minimizar llamadas al abrir la app.
- Background tasks sólo cuando el dispositivo esté cargando o con batería suficiente (WorkManager/BackgroundFetch).

## Modo offline y resiliencia
- Cachear últimas posiciones, eventos y tiles; mostrar indicador offline y bloquear acciones sensibles.
- Cola de acciones diferidas (ej. agregar nota/alerta) que se reenvían al recuperar conectividad.
- Política de expiración: invalidar caché geográfica >24h o cuando el usuario cambie de cuenta.

## Alertas y notificaciones
- Registrar token FCM/APNs tras login y enviarlo a `/api/devices/push-token`.
- Tópicos recomendados: `{tenant}/alerts`, `{tenant}/alerts/{vehicleId}` y `{tenant}/maintenance`.
- Deep links desde push hacia la pantalla de detalle o replay con parámetros `vehicleId` y `eventId`.

## Automatización de builds y distribución
- **React Native (Expo EAS)**: `eas build -p ios` / `eas build -p android` para binarios; `eas submit` a TestFlight/Play Store Internal.
- **Flutter + fastlane**:
  - iOS: `fastlane ios beta` genera IPA con certificados de App Store Connect y sube a TestFlight.
  - Android: `fastlane android beta` construye AAB firmado y publica en el track `internal`.
- Variables comunes: `API_BASE_URL`, `MAPBOX_TOKEN`, `SENTRY_DSN`, `FCM_KEY`, `OAUTH_CLIENT_ID` / `OAUTH_REDIRECT_URI`.
- Integrar pipelines en GitHub Actions utilizando `app-signing` secrets, cache de dependencias y artefactos de build.

## Validación QA
- Checklists de regresión: login/logout, expiración de sesión, manejo offline (matar conectividad y reanudar), replay de trazas, recepción de push y navegación por deep links.
- Pruebas en dispositivos reales con geolocalización simulada y throttling de red para validar optimizaciones.

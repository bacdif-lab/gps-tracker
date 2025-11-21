# Guía rápida para validar pipelines CI/CD

Este procedimiento sirve para verificar que los pipelines usan las credenciales correctas, firman y etiquetan los artefactos y reaccionan adecuadamente a fallos simulados. Ejecuta las acciones tanto en la rama principal como en una rama de prueba.

## 1. Preparación
- Revisa las variables/secretos configurados en el sistema de CI (App Store Connect, Play Store, firmantes web). Documenta nombre, propietario y fecha de última rotación.
- Ten a mano los certificados y perfiles de aprovisionamiento vigentes para iOS, así como las claves y `service accounts` necesarias para Android.
- Identifica el bucket o repositorio donde se publican artefactos de staging y producción.

## 2. Ejecución manual del pipeline
- Lanza el pipeline sobre la rama principal y luego sobre una rama de prueba creada desde `main`.
- Verifica que los jobs de **lint**, **tests**, **build web** y **build móvil** se inicien con los secretos esperados (p. ej., variables apuntando a credenciales de App Store/Play Store) y que no aparezcan advertencias de variables faltantes.
- Guarda capturas o logs de cada job con la información de entorno (sin exponer secretos) que confirme qué credenciales se usaron.

## 3. Validar firma y etiquetado de artefactos
- Confirmar que los artefactos generados (APK/AAB, IPA, bundles web) se firman con los certificados configurados y que el proceso incluye verificación de firma.
- Revisar que los artefactos resultantes se etiqueten con la versión/commit y se publiquen en los destinos de **staging** y **producción** según el pipeline.
- Para móviles: validar que el `bundleId`/`applicationId`, `versionCode`/`buildNumber` y perfil de firma correspondan al entorno objetivo.

## 4. Simulación de fallos
- Probar un caso de credencial rota o caducada (p. ej., variable sin valor o certificado revocado) en una rama de prueba y reejecutar el pipeline.
- Verificar que el pipeline falla de forma controlada, que se generan notificaciones (correo/chat) y que los logs señalan claramente la causa.
- Confirmar que no se publiquen artefactos incompletos o sin firma y que se respeten las políticas de retención.

## 5. Notificaciones y retención de artefactos
- Revisar la configuración de notificaciones por fallo/éxito y que se disparen a los canales esperados.
- Validar la política de retención: tiempo de conservación, versiones máximas y limpieza automatizada en los buckets o repositorios de artefactos.

## 6. Documentación de secretos y rotación
- Registrar los secretos usados por cada job (nombre en el CI, finalidad, propietario, fecha de creación/rotación, caducidad y procedimiento de renovación).
- Añadir recordatorios de rotación y responsables en la configuración del CI o en el gestor de secretos corporativo.
- Documentar los pasos para rotar credenciales y actualizar el pipeline sin interrumpir despliegues.

## 7. Evidencia y checklist final
- Conservar logs y hashes de artefactos generados en cada entorno.
- Rellenar una checklist con: rama ejecutada, estado de lint/tests/build, credenciales detectadas, firmas verificadas, notificaciones recibidas y retención confirmada.
- Anotar cualquier hallazgo o desviación y crear tareas de corrección en el backlog.

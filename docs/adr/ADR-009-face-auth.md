# ADR-009: Face-Auth como vía facial online

- Estado: aceptado
- Fecha: 2026-10-18

## Contexto

El reconocimiento facial no puede reemplazar la vía local: Face-Auth es un servicio externo, necesita Internet y tarda segundos. Tampoco queremos guardar video ni embeddings. Face-Auth ya es multi-tenant y verifica un `redirect_token` de un solo uso con `POST /api/v1/auth/token/verify/`.

La guía del servicio describe sobre todo un login de aplicación. En una puerta el navegador es un kiosco compartido, así que el token no puede convertirse en sesión ni guardarse en el dispositivo.

## Decisión

Cada organización se corresponde con una `Application` de Face-Auth. `FaceAuthIntegration` guarda `app_id`, la `api_key` cifrada con la llave de aplicación, las URLs y los interruptores `enabled`, `allow_panel_login` y `allow_kiosk_self_enrollment`. La `api_key` solo se escribe; no se lee de vuelta. El navegador usa únicamente el `app_id`.

La integración principal es headless. El componente `FaceCapture` (Fase 6) envía el clip directo a Face-Auth y reenvía a nuestra nube solo el `redirect_token`. La nube lo verifica una vez, lo asocia a `Credential(type=FACIAL, payload=<user_id>)` y le pide al Agente Edge la misma decisión de acceso que usaría una tarjeta, mediante el canal de comandos (ADR-010, Fase 2). El SSO alojado queda como respaldo para navegadores sin `MediaRecorder`.

El enrolamiento exige un email válido y único dentro de la organización. `GET /api/v1/employees/face-readiness` lista quién no cumple eso. Esta fase persiste los modelos y esa validación; las llamadas a Face-Auth llegan en la Fase 6.

El rostro es un factor único por defecto. Un kiosco es cualquier navegador con cámara. El login del panel con rostro es opcional por organización.

## Consecuencias

- No se almacenan imágenes ni vectores biométricos.
- Sin Internet, el kiosco no identifica por rostro y la puerta sigue operando con credenciales locales.
- Hay que coordinar con el equipo de Face-Auth la lista de la sección 4.3 del plan, en especial CORS, la confirmación del `redirect_token` y un entorno de pruebas. Mientras tanto el mock de `infra/faceauth-mock` cubre el contrato.
- El `redirect_token` se guarda solo como hash. La URL que usa el navegador y la que usa la nube pueden diferir (`server_api_url`). La baja del perfil en Face-Auth queda encolada hasta que exista el endpoint FA-4.
- `PendingFaceIdentity` queda reservado al respaldo hosted y no tiene API en esta fase.

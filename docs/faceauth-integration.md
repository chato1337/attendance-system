# Integración con Face-Auth

Face-Auth identifica a la persona con un clip de video. Este sistema no recibe ni guarda ese clip: el navegador lo envía directo a Face-Auth y solo reenvía un `redirect_token` de un solo uso. La nube lo verifica con la `api_key` de la organización y, en una puerta, le pide al agente la misma decisión que usaría una tarjeta.

## Alta del tenant

Por cada organización, el operador de Face-Auth crea una `Application` y entrega `app_id` y `api_key` por un canal seguro. En el panel, un administrador las carga en **Rostro**:

- `app_id` es público y lo usa el navegador.
- `api_key` se escribe y no se vuelve a leer. Queda cifrada con `FIELD_ENCRYPTION_KEY`.
- **URL para el navegador** es la que alcanza el kiosco o el panel (`http://localhost:8090/api/v1` con el mock).
- **URL para la nube** se usa solo si el proceso de la API no puede usar la misma dirección. En Docker, `http://faceauth-mock:8090/api/v1`. Si queda vacía, la nube usa la URL del navegador.

Antes de habilitar el rostro, **Preparación** debe estar vacía: cada empleado que lo vaya a usar necesita un correo válido y único en la organización.

## Orígenes y callbacks

Hay que pedir al equipo de Face-Auth (FA-1) que autorice estos orígenes CORS, los que muestra la pantalla Rostro:

- `http://localhost:5173`
- `http://localhost:8080`

El flujo alojado, solo para navegadores sin `MediaRecorder`, redirige a estas rutas fijas:

- `/auth/faceauth/return`
- `/kiosk/callback`
- `/enroll/faceauth/callback`

El token llega en la query y la página lo quita de la barra de inmediato. No se guarda en `localStorage`.

## Clip

De 2 a 4 segundos, webm o mp4, al menos 320×240 y como máximo 15 MB. La persona debe parpadear. Esos controles los hace Face-Auth; la guía del óvalo en pantalla es solo de ayuda.

## Kiosco

1. En **Kioscos**, cree uno asociado a una puerta con rostro habilitado y copie el token.
2. Abra `/kiosk` en el dispositivo de la puerta y pegue el token.
3. La persona pulsa **Ingresar con rostro**. El resultado concedido o denegado vuelve en la misma pantalla.
4. Sin Internet, o con Face-Auth apagado, el kiosco pide usar la tarjeta. La puerta sigue operando con el agente.

El permiso de cámara se informa en el latido. Un kiosco con permiso denegado aparece como «sin cámara».

## Enrolamiento

Desde la ficha del empleado, **Enrolar rostro** pide un código al correo y luego el clip. El asistente puede copiar un enlace `/enrolar/<sesión>` para que otra persona con sesión en el panel lo abra en su dispositivo; caduca a los 15 minutos. El mismo asistente está en el kiosco si la organización permite el autoregistro. El `user_id` que devuelve Face-Auth queda como credencial `FACIAL`.

Si el registro falla con `email_taken` o `duplicate_biometric`, la sesión queda registrada con ese código y el formulario no se vacía: solo hay que volver a capturar cuando el error es del video.

## Login del panel

Si la organización activa «Permitir ingreso al panel con rostro», la pantalla de login pide el slug y usa el mismo componente de captura. No se crean usuarios nuevos: el correo o el `user_id` ya vinculado deben corresponder a alguien con membresía.

## Mock local

```bash
python infra/faceauth-mock/server.py
```

Queda en `http://localhost:8090`. También sube con `docker compose`. Acepta cualquier clip, reconoce a un usuario de demostración y devuelve el código OTP `000000` en `debug_code`. Ese campo no existe en Face-Auth real.

Cabeceras de prueba: `X-Test-Error` (`no_match`, `spoof_detected`, `email_taken`, `rate_limited`), `X-Test-User-Id`, `X-Test-Email`.

## Rotación y bajas

Para rotar la `api_key`, escríbala de nuevo en Rostro y pulse **Probar conexión**. La anterior deja de usarse en el momento del guardado.

Al desactivar una credencial facial o al empleado, el sistema anota la baja en `FaceAuthPendingDeletion`. Face-Auth todavía no ofrece el endpoint para borrar el perfil (FA-4); hasta entonces la baja se completa con el operador de ese servicio y el agente ya rechaza la credencial inactiva por el delta.

## Operación

La pantalla Rostro resume las últimas 24 horas: estados de identificación, códigos de Face-Auth, p95 de la verificación, permiso de cámara de los kioscos y bajas biométricas pendientes. El detalle sale de `GET /api/v1/faceauth-integration/metrics/`.

## Errores

| Código | Qué hacer |
| --- | --- |
| `token_already_used` | No reenviar el token. El primer resultado es el válido. |
| `invalid_token` | Volver a capturar. El token dura dos minutos y es de un solo uso. |
| `app_inactive` | Revisar el tenant con el operador de Face-Auth. |
| `429` / `rate_limited` | Esperar y, si una sede lo repite, pedir el ajuste de límite (FA-3). |
| `NODE_OFFLINE` | El kiosco muestra la denegación y queda una marcación denegada. La puerta no abrió. |

## Solicitudes abiertas

FA-1 (CORS), FA-5 (confirmar el `redirect_token` sin `redirect_uri`) y FA-8 (staging) siguen pendientes para probar contra Face-Auth real. El mock cubre el contrato mientras tanto. El resto (FA-2, FA-3, FA-4, FA-6, FA-7, FA-9, FA-10) no bloquea esta entrega.

# Guía de integración — Aplicaciones cliente

> Audiencia: equipos de desarrollo de aplicaciones de terceros ("apps cliente") que quieren delegar el login/registro de sus usuarios en Face-Auth, el servicio de autenticación biométrica SSO multi-tenant.
>
> Referencias: diseño en [`ARCHITECTURE.md`](ARCHITECTURE.md) · operación de tenants en [`OPERATIONS.md`](OPERATIONS.md) · contrato OpenAPI navegable en `/api/docs/` (Swagger UI) y `/api/redoc/`.

En esta guía, `<FACEAUTH_WEB>` es la URL del frontend SSO de Face-Auth (dev: `http://localhost:<FRONTEND_PORT>`, default `5173`) y `<FACEAUTH_API>` la del backend (dev: `http://localhost:<BACKEND_PORT>`, default `8000`). Los puertos se configuran en el `.env` raíz.

---

## 1. Cómo funciona la integración

Face-Auth autentica personas con un clip corto de video (captura pasiva: la cámara detecta el rostro y un parpadeo dispara la captura automáticamente). Tu aplicación **nunca** maneja contraseñas ni video: recibe un token firmado cuando el usuario se autentica.

Cada app cliente es un **tenant** (`Application`) con aislamiento total: los usuarios y perfiles biométricos registrados en tu `app_id` no existen para otros tenants, y viceversa. La misma persona puede registrarse de forma independiente en dos aplicaciones distintas.

Hay dos formas de integrarse:

| Modo | Qué haces | Recomendado para |
|---|---|---|
| **A. SSO hosted** (recomendado) | Rediriges el navegador al frontend de Face-Auth y recibes un token en tu callback | La mayoría de integraciones; cero código de cámara/biometría |
| **B. API REST directa** | Tu propio frontend captura el video y llama a la API de Face-Auth | Apps que necesitan UI de captura propia (p. ej. móvil nativo) |

En ambos modos Face-Auth **prueba identidad** (quién es la persona). Si tu aplicación ya tiene su propia gestión de autenticación/autorización (sesiones, cookies, JWT propios, roles, etc.), el patrón soportado es un **intercambio de tokens**: validas el token de Face-Auth en tu backend y, si es válido, **creas la sesión con tu login propio**. Face-Auth no emite ni gestiona la sesión de tu app; solo te entrega una prueba de identidad de un solo uso (§3.4).

---

## 2. Requisitos previos (alta del tenant)

Solicita al operador de la plataforma Face-Auth el alta de tu aplicación (se hace vía panel admin o CLI, ver [`OPERATIONS.md`](OPERATIONS.md)). Debes entregar:

1. **Nombre** de tu aplicación.
2. **`redirect_uris`**: la lista exacta de URLs de callback a las que Face-Auth puede redirigir tras un login exitoso. La comparación es **whitelist exacta** (scheme + host + path + query, normalizados) — no por prefijo. `https://miapp.com/callback` **no** autoriza `https://miapp.com/callback/extra` ni `https://miapp.com/otra`.

Recibirás:

- **`app_id`** (ej. `app_AbC123...`): identificador público de tu tenant. Va en URLs y requests; no es secreto.
- **`api_key`**: secreto de tenant, entregado **una sola vez**. Guárdalo en tu gestor de secretos: la necesitas para verificar tokens en tu backend (§3.3). Nunca la expongas en el navegador; si se compromete, pide su rotación.

Tu tenant también tiene umbrales configurables (`liveness_threshold`, `match_threshold`) que el operador puede ajustar si tu población de usuarios sufre falsos rechazos.

---

## 3. Modo A — SSO hosted (recomendado)

### 3.1 Iniciar el flujo

Redirige el navegador del usuario al frontend de Face-Auth con tu `app_id` y tu `redirect_uri` whitelisteada:

```
# Login (usuarios ya registrados)
<FACEAUTH_WEB>/login?app_id=<APP_ID>&redirect_uri=<URL_ENCODED_CALLBACK>

# Registro (primera vez: formulario + captura biométrica)
<FACEAUTH_WEB>/register?app_id=<APP_ID>&redirect_uri=<URL_ENCODED_CALLBACK>
```

Ejemplo:

```
https://faceauth.example.com/login?app_id=app_AbC123&redirect_uri=https%3A%2F%2Fmiapp.com%2Fauth%2Fcallback
```

Face-Auth valida el `app_id` (404 propio si no existe o está inactivo), enciende la cámara, y captura automáticamente cuando el usuario parpadea con el rostro alineado. No hay botón de "grabar".

### 3.2 Recibir el callback

Tras autenticación exitosa, Face-Auth redirige a tu `redirect_uri` agregando el token como query param:

```
https://miapp.com/auth/callback?token=<SSO_REDIRECT_TOKEN>
```

El `token` es un **JWT de un solo uso** con TTL de **2 minutos** y estos claims:

| Claim | Contenido |
|---|---|
| `token_type` | `"sso_redirect"` |
| `purpose` | `"sso_redirect"` |
| `user_id` | UUID del usuario en Face-Auth (estable por tenant; úsalo como clave de identidad) |
| `app_id` | Tu `app_id` |
| `email` | Email del usuario |
| `jti`, `nonce` | Identificadores únicos del token (anti-replay) |
| `exp` | Expiración (emisión + 2 min) |

Si el usuario llega a tu callback **sin** `token`, trata la sesión como no autenticada y vuelve a iniciar el flujo.

### 3.3 Validar el token en tu backend

Tu endpoint de callback debe validar el token **en el servidor** (nunca confíes en el frontend) antes de crear la sesión local. Para eso existe el endpoint de verificación server-to-server, autenticado con tu `api_key`:

```bash
curl -X POST "<FACEAUTH_API>/api/v1/auth/token/verify/" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: <TU_API_KEY>" \
  -d '{"app_id": "app_AbC123", "token": "<TOKEN_DEL_CALLBACK>"}'
```

Respuesta `200` (token válido y **consumido** — ver abajo):

```json
{
  "valid": true,
  "user_id": "0b0f6e0e-…",
  "app_id": "app_AbC123",
  "email": "ada@example.com",
  "first_name": "Ada",
  "last_name": "Lovelace",
  "expires_at": "2026-07-30T23:41:12Z"
}
```

El endpoint verifica por ti: firma, expiración, `purpose == "sso_redirect"` (un `access`/`refresh` token se rechaza), que el token pertenezca a **tu** tenant, y que el usuario siga activo. Además aplica **consumo de un solo uso**: la primera verificación exitosa registra el `jti` y cualquier reintento devuelve `401 token_already_used` — no necesitas implementar anti-replay propio, pero **no verifiques el mismo token dos veces** (guarda el resultado).

Errores posibles (payload `{code, message, field}`):

| HTTP | `code` | Significado |
|---|---|---|
| 401 | `invalid_api_key` | Header `X-Api-Key` ausente o incorrecto |
| 401 | `invalid_token` | Firma inválida, expirado, tipo incorrecto o de otro tenant |
| 401 | `token_already_used` | El token ya fue consumido (posible replay) |
| 401 | `user_inactive` | El usuario fue desactivado en tu tenant |

Con la respuesta `200`, tienes una identidad verificada. El siguiente paso es crear la sesión de **tu** aplicación (§3.4).

> **Importante:** la `api_key` es un secreto de servidor. Nunca llames a este endpoint desde el navegador ni la incluyas en código cliente. La evolución a code-exchange OAuth2 completo (authorization code → token) sigue registrada en [`MASTER_PLAN.md`](MASTER_PLAN.md); el flujo actual es el equivalente funcional: JWT de un solo uso + verificación server-to-server.

### 3.4 Intercambio de tokens → sesión propia de tu aplicación

Usa este flujo cuando tu app **ya tiene** autenticación/autorización propia (Django session, JWT interno, cookies firmadas, Spring Security, Auth0/Cognito como IdP secundario, etc.) y Face-Auth actúa solo como factor de identidad biométrica.

```
Usuario                Tu frontend              Face-Auth                 Tu backend
   |                        |                        |                          |
   |  "Iniciar sesión"      |                        |                          |
   |----------------------->|                        |                          |
   |                        |  redirect /login?app_id&redirect_uri              |
   |                        |----------------------->|                          |
   |                   captura biométrica            |                          |
   |<------------------------------------------------|                          |
   |                        |  callback?token=…      |                          |
   |                        |<-----------------------|                          |
   |                        |  POST /auth/callback {token}                      |
   |                        |-------------------------------------------------->|
   |                        |                        |  POST /token/verify/     |
   |                        |                        |<-------------------------|
   |                        |                        |  200 {user_id, email…}   |
   |                        |                        |------------------------->|
   |                        |                        |     crea/actualiza usuario
   |                        |                        |     emite TU sesión
   |                        |  Set-Cookie / JWT propio                          |
   |                        |<--------------------------------------------------|
   |                   app autenticada con TU login                             |
```

**Pasos en tu backend (callback):**

1. Recibe el `token` del query (o del body si tu frontend lo reenvía).
2. Llama a `POST /api/v1/auth/token/verify/` con tu `api_key` (§3.3). Si no es `200`, rechaza (401/403) y no crees sesión.
3. Con `user_id` (UUID estable por tenant) busca o crea tu usuario interno (`external_id` / `faceauth_user_id` → tu tabla de usuarios). Usa `email`, `first_name`, `last_name` para sincronizar perfil si te conviene.
4. Emite **tu** sesión: cookie de sesión, JWT firmado con tu secreto, ticket de tu IdP, etc. Aplica aquí tus roles, permisos y políticas de autorización.
5. Responde al navegador ya autenticado en tu dominio (redirect a home, JSON con tu access token, etc.).

Ejemplo mínimo (pseudocódigo; adapta al stack de tu app):

```python
# POST /auth/faceauth/callback  (tu backend)
def faceauth_callback(request):
    token = request.GET.get("token") or request.data.get("token")
    if not token:
        return unauthorized("missing_token")

    # 1) Intercambio: prueba de identidad Face-Auth → claims confiables
    verify = httpx.post(
        f"{FACEAUTH_API}/api/v1/auth/token/verify/",
        headers={"X-Api-Key": FACEAUTH_API_KEY, "Content-Type": "application/json"},
        json={"app_id": FACEAUTH_APP_ID, "token": token},
    )
    if verify.status_code != 200:
        return unauthorized(verify.json().get("code", "invalid_token"))

    identity = verify.json()  # user_id, email, first_name, last_name, …

    # 2) Mapeo a tu modelo de usuarios + login propio
    user, _ = User.objects.get_or_create(
        faceauth_user_id=identity["user_id"],
        defaults={"email": identity["email"], "first_name": identity["first_name"], …},
    )
    # opcional: actualizar email/nombre si cambiaron en Face-Auth

    # 3) Sesión de TU aplicación (no reutilices el JWT de Face-Auth como sesión)
    login(request, user)                    # p. ej. sesión Django
    # o: return {"access": issue_my_jwt(user), "refresh": …}

    return redirect("/app")
```

**Reglas importantes:**

| Qué | Detalle |
|---|---|
| Quién crea la sesión | **Tu backend**, después del `verify` exitoso |
| Qué token usa el navegador después | El de **tu** app (cookie/JWT propio). Descarta el `token` del callback; ya fue consumido |
| Access/refresh de Face-Auth | Solo necesarios si vas a llamar APIs de Face-Auth después; **no** son la sesión de tu producto |
| Clave de enlace | Persiste `user_id` de Face-Auth como identificador estable; el email puede cambiar |
| Un solo uso | El `verify` consume el token: no lo reenvíes ni lo verifiques dos veces |
| Autorización | Roles, scopes y permisos siguen siendo responsabilidad de tu app |

Este patrón es el contrato soportado hoy. No hace falta (ni está disponible) un endpoint OAuth2 `token` de authorization-code; `token/verify/` es el puente de intercambio.

### 3.5 Sin `redirect_uri` (modo embebido)

Si abres el flujo sin `redirect_uri`, no hay redirección: los tokens quedan en la sesión del navegador dentro de Face-Auth. Útil solo para demos o cuando Face-Auth es tu única UI — **no** aplica al intercambio de §3.4.

---

## 4. Modo B — API REST directa

Si construyes tu propia captura (p. ej. app móvil), consume la API directamente. Contrato completo y ejecutable en `<FACEAUTH_API>/api/docs/`.

### 4.1 Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/v1/applications/{app_id}/` | Validar tenant antes de mostrar UI (público) |
| POST | `/api/v1/auth/login/` | Login biométrico (`multipart/form-data`) |
| POST | `/api/v1/auth/register/` | Registro biométrico (`multipart/form-data`) |
| POST | `/api/v1/auth/token/refresh/` | Renovar access token (JSON) |
| POST | `/api/v1/auth/token/verify/` | Verificar token del callback SSO (JSON + `X-Api-Key`; puente para sesión propia, ver §3.3–§3.4) |

### 4.2 Requisitos del video

El backend valida el clip antes de procesarlo (rechazos → `400`/`422` con motivo):

- Formato **mp4 o webm**, tamaño máximo **15 MB**.
- Duración **1–6 s** (recomendado 2–4 s).
- Resolución mínima **320×240**, iluminación razonable.
- El usuario debe **parpadear** y no quedarse totalmente estático durante el clip (liveness activo); una foto o una pantalla reproducida se rechaza (liveness pasivo).

### 4.3 Login

```bash
curl -X POST "<FACEAUTH_API>/api/v1/auth/login/" \
  -H "X-App-Id: app_AbC123" \
  -F "app_id=app_AbC123" \
  -F "video=@clip.webm;type=video/webm" \
  -F "redirect_uri=https://miapp.com/auth/callback"   # opcional
```

Respuesta `200`:

```json
{
  "user_id": "0b0f6e0e-…",
  "email": "ada@example.com",
  "first_name": "Ada",
  "last_name": "Lovelace",
  "distance": 0.31,
  "liveness": {"passed": true, "active_score": 0.93, "passive_score": 0.97, "reason": null},
  "tokens": {
    "access": "<JWT 30 min>",
    "refresh": "<JWT 7 días>",
    "redirect_token": "<JWT 2 min, purpose=sso_redirect>",
    "redirect_url": "https://miapp.com/auth/callback?token=…"  // null si no enviaste redirect_uri
  }
}
```

`access`/`refresh` llevan claims `user_id`, `app_id`, `email`. Renueva con:

```bash
curl -X POST "<FACEAUTH_API>/api/v1/auth/token/refresh/" \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<REFRESH_TOKEN>"}'
```

### 4.4 Registro

El enrolamiento exige un OTP de email **antes** de persistir el perfil biométrico.

```bash
# 1) Solicitar código (crea TenantUser pendiente si no existe)
curl -X POST "<FACEAUTH_API>/api/v1/otp/request/" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "app_AbC123",
    "purpose": "email_verify",
    "email": "ada@example.com",
    "first_name": "Ada",
    "last_name": "Lovelace"
  }'

# 2) Validar en UI (no consume el código)
curl -X POST "<FACEAUTH_API>/api/v1/otp/verify/" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "app_AbC123",
    "purpose": "email_verify",
    "email": "ada@example.com",
    "code": "123456"
  }'

# 3) Registrar con el mismo código en el payload
curl -X POST "<FACEAUTH_API>/api/v1/auth/register/" \
  -H "X-App-Id: app_AbC123" \
  -F "app_id=app_AbC123" \
  -F "first_name=Ada" \
  -F "last_name=Lovelace" \
  -F "email=ada@example.com" \
  -F "phone=+57123456789" \
  -F "otp_code=123456" \
  -F "video=@clip.webm;type=video/webm"
```

Respuesta `201` con el mismo shape de `tokens` más `quality_score`. El email es único **por tenant**; un rostro ya enrolado en tu `app_id` se rechaza como duplicado. En el modo hosted SSO, Face-Auth muestra el paso OTP; si integras la API directo, debes pedir y reenviar `otp_code`.

**Regla de UX en errores de registro:** no resetees el formulario. Solo el video debe recapturarse; conserva los datos que el usuario ya escribió (para `email_taken`, regresa el foco al campo email; para errores `otp_*`, vuelve al paso del código).

---

## 5. Manejo de errores

Todos los errores usan el payload uniforme:

```json
{"code": "spoof_detected", "message": "Liveness activo fallido: no se detectó parpadeo", "field": "video"}
```

| HTTP | `code` | Significado | Acción sugerida en tu app |
|---|---|---|---|
| 400 | `invalid_video` | Video corrupto / formato no soportado | Recapturar |
| 400 | `app_inactive` | Tenant desactivado | Contactar al operador |
| 400 | `invalid_redirect_uri` | `redirect_uri` fuera de la whitelist exacta | Corregir configuración (ver §2) |
| 401 | `no_match` | Liveness OK pero el rostro no coincide con ningún usuario del tenant | Ofrecer registro o reintento |
| 401 | `invalid_token` | Refresh token inválido/expirado | Re-autenticar |
| 404 | `app_not_found` | `app_id` inexistente | Corregir configuración |
| 400 | `otp_invalid` / `otp_expired` / `otp_locked` / `otp_not_found` | Código OTP incorrecto, vencido, bloqueado o no solicitado | Volver al paso OTP o reenviar |
| 409 | `email_taken` | Email ya registrado en tu tenant | Mostrar error en el campo email, conservar formulario |
| 409 | `duplicate_biometric` | El rostro ya está enrolado en tu tenant | Sugerir login |
| 422 | `low_quality_capture` | Iluminación/encuadre/fps insuficientes | Mostrar el `message` (es accionable) y recapturar |
| 422 | `spoof_detected` | Liveness activo o pasivo fallido | Recapturar (parpadear, no usar fotos/pantallas) |
| 422 | `face_not_found` | No hay rostro consistente en el clip | Recapturar centrando el rostro |
| 429 | — | Rate limit excedido | Reintentar con backoff |

En el modo SSO hosted estos errores los muestra la propia UI de Face-Auth y el flujo se reinicia solo; tu app solo ve el resultado final (callback con token o usuario que abandona).

---

## 6. Límites y seguridad

- **Rate limiting:** por defecto **30 requests/min por `app_id` + IP** en login/registro (configurable por despliegue). OTP: máximo **3 códigos / 5 min por usuario** más un tope de cortesía por IP. Diseña reintentos con backoff.
- **CORS:** si llamas a la API desde un navegador en tu propio dominio, tu origen debe estar en la whitelist de CORS del despliegue; solicítalo al operador junto con el alta del tenant.
- **Privacidad del video:** Face-Auth procesa el clip en memoria y no lo persiste; solo se almacena el embedding facial (vector de 512 dimensiones) del enrolamiento. No guardes el clip en tu lado tampoco.
- **Zero-Trust:** la detección de parpadeo del frontend es solo conveniencia de UX; toda la validación biométrica (liveness activo + pasivo + matching) ocurre en el backend sobre el video recibido. No asumas que un clip que "pasó" en el cliente será aceptado.
- **Tokens:** trata `access`/`refresh`/`redirect_token` como credenciales. Transporta siempre sobre HTTPS; el `redirect_token` viaja en query string, así que evita loggear URLs de callback completas.

---

## 7. Checklist de integración

- [ ] `app_id` recibido y `redirect_uris` registradas (coincidencia exacta, sin fragmentos `#`, solo http/https).
- [ ] `api_key` guardada en gestor de secretos (no en el repo).
- [ ] Redirección a `<FACEAUTH_WEB>/login?app_id=…&redirect_uri=…` con la URI url-encodeada.
- [ ] Callback llama a `POST /api/v1/auth/token/verify/` con la `api_key` (desde el servidor) y solo crea sesión con respuesta `200`.
- [ ] Intercambio (§3.4): tras `verify` 200, emites **tu** sesión/login propio; no reutilizas el JWT de Face-Auth como cookie de tu app.
- [ ] Mapeo persistente `user_id` (UUID Face-Auth) → usuario interno de tu app.
- [ ] Flujo de registro enlazado (`/register?app_id=…`) para usuarios nuevos.
- [ ] Manejo de "usuario llega al callback sin token" (abandono/cancelación).
- [ ] (Modo B) formulario conserva datos ante errores; video cumple §4.2; backoff ante 429.
- [ ] Probado end-to-end en el entorno de staging del operador antes de producción.

---

## 8. Soporte

- Contrato vivo: `<FACEAUTH_API>/api/docs/` (Swagger, permite probar login/registro subiendo un video) y `<FACEAUTH_API>/api/schema/` (OpenAPI JSON para generar clientes tipados, p. ej. `openapi-typescript`).
- Cambios de configuración del tenant (redirect URIs, umbrales, rotación de `api_key`): canal con el operador de la plataforma ([`OPERATIONS.md`](OPERATIONS.md)).

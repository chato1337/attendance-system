"""Mock de Face-Auth para desarrollo y pruebas.

Implementa el contrato de docs/face-auth.md en modo headless: login, registro,
OTP y verify de un solo uso. No persiste video.

Identidad de prueba:
- cabecera X-Test-User-Id y X-Test-Email
- cabecera X-Test-Error: no_match, spoof_detected, email_taken, rate_limited
- sin cabeceras, el login reconoce a Ada (user fijo de demostración)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST = "0.0.0.0"
PORT = 8090
SECRET = b"faceauth-mock-dev-secret"
DEMO_USER = "11111111-1111-4111-8111-111111111111"
DEMO_EMAIL = "ada@faceauth.test"
CONSUMED: set[str] = set()
USERS: dict[tuple[str, str], str] = {}
OTP: dict[tuple[str, str], str] = {}


def b64(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def issue_token(user_id: str, email: str, app_id: str) -> str:
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = {
        "token_type": "sso_redirect",
        "purpose": "sso_redirect",
        "user_id": user_id,
        "app_id": app_id,
        "email": email,
        "jti": str(uuid.uuid4()),
        "nonce": str(uuid.uuid4()),
        "exp": int(time.time()) + 120,
    }
    body = b64(json.dumps(payload).encode())
    signature = b64(hmac.new(SECRET, f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{signature}"


def read_token(token: str) -> dict | None:
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        return None
    header, body, signature = parts
    expected = b64(hmac.new(SECRET, f"{header}.{body}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        return None
    padded = body + "=" * (-len(body) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("purpose") != "sso_redirect" or int(payload.get("exp", 0)) < time.time():
        return None
    return payload


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"ok": True})
            return
        if parsed.path in {"/login", "/register"}:
            self._hosted(parsed)
            return
        prefix = "/api/v1/applications/"
        if parsed.path.startswith(prefix):
            app_id = parsed.path[len(prefix) :].strip("/")
            if app_id in {"", "missing"}:
                self._error(404, "app_not_found", "Aplicación no encontrada.")
                return
            if app_id == "inactive":
                self._error(400, "app_inactive", "Aplicación inactiva.")
                return
            self._json(200, {"app_id": app_id, "name": f"Mock {app_id}", "is_active": True})
            return
        self._error(404, "not_found", "Ruta no encontrada.")

    def do_POST(self):
        path = urlparse(self.path).path
        forced = self.headers.get("X-Test-Error", "")
        if forced == "rate_limited":
            self._error(429, "rate_limited", "Demasiadas solicitudes.")
            return
        if path == "/api/v1/auth/token/verify/":
            self._verify()
            return
        if path == "/api/v1/otp/request/":
            self._otp_request()
            return
        if path == "/api/v1/otp/verify/":
            self._otp_verify()
            return
        if path in {"/api/v1/auth/login/", "/api/v1/auth/register/"}:
            self._biometric(register=path.endswith("register/"))
            return
        self._error(404, "not_found", "Ruta no encontrada.")

    def _verify(self):
        body = self._json_body()
        api_key = self.headers.get("X-Api-Key", "")
        if not api_key or api_key == "invalid":
            self._error(401, "invalid_api_key", "API key inválida.")
            return
        payload = read_token(str(body.get("token") or ""))
        if payload is None or payload.get("app_id") != body.get("app_id"):
            self._error(401, "invalid_token", "Token inválido.")
            return
        jti = str(payload["jti"])
        if jti in CONSUMED:
            self._error(401, "token_already_used", "El token ya fue utilizado.")
            return
        CONSUMED.add(jti)
        self._json(
            200,
            {
                "valid": True,
                "user_id": payload["user_id"],
                "app_id": payload["app_id"],
                "email": payload["email"],
                "first_name": "Ada",
                "last_name": "Lovelace",
            },
        )

    def _otp_request(self):
        body = self._json_body()
        code = "000000"
        OTP[(str(body.get("app_id")), str(body.get("email")).lower())] = code
        self._json(200, {"sent": True, "debug_code": code})

    def _otp_verify(self):
        body = self._json_body()
        expected = OTP.get((str(body.get("app_id")), str(body.get("email")).lower()))
        if body.get("code") not in {expected, "000000"}:
            self._error(400, "otp_invalid", "Código incorrecto.")
            return
        self._json(200, {"valid": True})

    def _biometric(self, register: bool):
        forced = self.headers.get("X-Test-Error", "")
        length = int(self.headers.get("Content-Length") or "0")
        if length > 15 * 1024 * 1024:
            self._error(400, "invalid_video", "El video supera 15 MB.")
            return
        self.rfile.read(length)
        if forced in {"no_match", "spoof_detected", "low_quality_capture", "face_not_found"}:
            status = 422 if forced != "no_match" else 401
            self._error(status, forced, "Captura rechazada.")
            return
        if forced == "email_taken":
            self._error(409, "email_taken", "El correo ya está registrado.")
            return
        app_id = self.headers.get("X-App-Id") or "app_demo"
        user_id = self.headers.get("X-Test-User-Id") or DEMO_USER
        email = self.headers.get("X-Test-Email") or DEMO_EMAIL
        if register:
            key = (app_id, email.lower())
            if key in USERS:
                self._error(409, "email_taken", "El correo ya está registrado.")
                return
            USERS[key] = user_id
        token = issue_token(user_id, email, app_id)
        self._json(
            201 if register else 200,
            {
                "user_id": user_id,
                "email": email,
                "first_name": "Ada",
                "last_name": "Lovelace",
                "tokens": {"redirect_token": token, "access": "discard", "refresh": "discard"},
            },
        )

    def _hosted(self, parsed):
        query = parse_qs(parsed.query)
        redirect = (query.get("redirect_uri") or [""])[0]
        app_id = (query.get("app_id") or ["app_demo"])[0]
        token = issue_token(DEMO_USER, DEMO_EMAIL, app_id)
        target = f"{redirect}{'&' if '?' in redirect else '?'}token={token}" if redirect else "/"
        html = f"""<!doctype html>
<html lang="es"><body>
<p>Mock de Face-Auth. Este flujo alojado es el respaldo.</p>
<p><a href="{target}">Continuar</a></p>
</body></html>"""
        encoded = html.encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _error(self, status: int, code: str, message: str):
        self._json(status, {"code": code, "message": message})

    def _json(self, status: int, payload: dict):
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def _send(self, status: int, body: bytes):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-App-Id, X-Api-Key, X-Test-Error, X-Test-User-Id, X-Test-Email")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

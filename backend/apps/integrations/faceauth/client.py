import json
import urllib.error
import urllib.request

from django.conf import settings

from apps.integrations.models import FaceAuthIntegration


class FaceAuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_request(method: str, url: str, data: bytes | None, headers: dict, timeout: float):
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"code": "invalid_response", "message": raw[:300]}
        return exc.code, body
    except urllib.error.URLError as exc:
        raise FaceAuthError("unavailable", "Face-Auth no responde.", 503) from exc


def server_base(integration: FaceAuthIntegration) -> str:
    return (integration.server_api_url or integration.api_url).rstrip("/")


class FaceAuthClient:
    """Cliente server-to-server. No reintenta verify: el token es de un solo uso."""

    def __init__(self, integration: FaceAuthIntegration):
        self.integration = integration
        self.base = server_base(integration)
        self.app_id = integration.app_id
        self.api_key = integration.api_key
        self.timeout = settings.FACEAUTH_VERIFY_TIMEOUT_SECONDS

    def verify_token(self, token: str) -> dict:
        status, body = self._json(
            "POST",
            f"{self.base}/auth/token/verify/",
            {"app_id": self.app_id, "token": token},
            {"X-Api-Key": self.api_key, "Content-Type": "application/json"},
        )
        if status != 200:
            raise _error(status, body)
        if not body.get("user_id"):
            raise FaceAuthError("invalid_token", "La verificación no trajo user_id.", 401)
        return body

    def get_application(self) -> dict:
        status, body = self._json(
            "GET",
            f"{self.base}/applications/{self.app_id}/",
            None,
            {"X-App-Id": self.app_id, "Accept": "application/json"},
        )
        if status != 200:
            raise _error(status, body)
        return body

    def _json(self, method: str, url: str, payload: dict | None, headers: dict):
        data = None if payload is None else json.dumps(payload).encode()
        return http_request(method, url, data, headers, self.timeout)


def _error(status: int, body: dict) -> FaceAuthError:
    if not isinstance(body, dict):
        body = {}
    code = str(body.get("code") or ("rate_limited" if status == 429 else "invalid_token"))
    message = str(body.get("message") or "Face-Auth rechazó la solicitud.")
    return FaceAuthError(code[:64], message[:500], status)

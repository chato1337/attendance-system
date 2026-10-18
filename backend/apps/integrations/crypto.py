from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_cache: dict[str, Fernet] = {}


def fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, bytes):
        key = key.decode()
    cached = _cache.get(key)
    if cached is None:
        cached = Fernet(key.encode())
        _cache[key] = cached
    return cached


def encrypt_str(value: str) -> str:
    return fernet().encrypt(value.encode()).decode()


def decrypt_str(value: str) -> str:
    try:
        return fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("No se pudo descifrar el valor.") from exc

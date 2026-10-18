import hashlib
import secrets


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def generate_secret() -> tuple[str, str]:
    plain = secrets.token_urlsafe(32)
    return plain, hash_secret(plain)

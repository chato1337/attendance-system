from django.core import signing

EXPORT_SALT = "attendance-report-export"


def sign_export(job_id) -> str:
    return signing.TimestampSigner(salt=EXPORT_SALT).sign(str(job_id))


def unsign_export(token: str) -> str | None:
    if not token:
        return None
    try:
        return signing.TimestampSigner(salt=EXPORT_SALT).unsign(token, max_age=60 * 60 * 48)
    except signing.BadSignature:
        return None

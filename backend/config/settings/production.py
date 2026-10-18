from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import DEV_FERNET_KEY, DEV_SECRET_KEY, FIELD_ENCRYPTION_KEY, SECRET_KEY

DEBUG = False
ALLOW_DEMO_SEED = False

if SECRET_KEY == DEV_SECRET_KEY:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY para producción.")
if FIELD_ENCRYPTION_KEY == DEV_FERNET_KEY:
    raise ImproperlyConfigured("Defina FIELD_ENCRYPTION_KEY para producción.")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

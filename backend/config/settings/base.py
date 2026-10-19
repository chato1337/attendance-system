import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEV_SECRET_KEY = "dev-only-attendance-secret-key-32b"
DEV_FERNET_KEY = "9ABHw7khRINU5hwTHBX-eRy9vK8ttpqxQIzsHU3CNLQ="


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def database_from_env() -> dict:
    url = os.environ.get("DATABASE_URL")
    if url:
        parsed = urlparse(url)
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or "5432"),
        }
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "attendance"),
        "USER": os.environ.get("POSTGRES_USER", "attendance"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "attendance"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", DEV_SECRET_KEY)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:8000,http://localhost:8080",
)

FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", DEV_FERNET_KEY)
FACEAUTH_WEB_URL = os.environ.get("FACEAUTH_WEB_URL", "http://localhost:8090")
FACEAUTH_API_URL = os.environ.get("FACEAUTH_API_URL", "http://localhost:8090/api/v1")
FACEAUTH_VERIFY_TIMEOUT_SECONDS = float(os.environ.get("FACEAUTH_VERIFY_TIMEOUT_SECONDS", "3"))
FACE_IDENTIFY_TIMEOUT_SECONDS = float(os.environ.get("FACE_IDENTIFY_TIMEOUT_SECONDS", "8"))
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
ALLOW_DEMO_SEED = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "channels",
    "apps.common.apps.CommonConfig",
    "apps.tenants.apps.TenantsConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.people.apps.PeopleConfig",
    "apps.access.apps.AccessConfig",
    "apps.kiosk.apps.KioskConfig",
    "apps.integrations.apps.IntegrationsConfig",
    "apps.sync.apps.SyncConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.tenants.middleware.TenantContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
AUTH_USER_MODEL = "accounts.User"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {"default": database_from_env()}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "mark-stale-nodes-offline": {
        "task": "apps.sync.tasks.mark_stale_nodes_offline_task",
        "schedule": 60.0,
    },
    "expire-edge-commands": {
        "task": "apps.sync.tasks.expire_edge_commands",
        "schedule": 5.0,
    },
    "reconcile-occupancy": {
        "task": "apps.access.tasks.reconcile_occupancy_task",
        "schedule": crontab(hour=3, minute=20),
    },
}

EDGE_DELTA_DEFAULT_LIMIT = int(os.environ.get("EDGE_DELTA_DEFAULT_LIMIT", "500"))
EDGE_DELTA_MAX_LIMIT = int(os.environ.get("EDGE_DELTA_MAX_LIMIT", "1000"))
EDGE_LOG_BATCH_MAX = int(os.environ.get("EDGE_LOG_BATCH_MAX", "500"))
EDGE_HEARTBEAT_TIMEOUT_MINUTES = int(os.environ.get("EDGE_HEARTBEAT_TIMEOUT_MINUTES", "3"))
EDGE_COMMAND_POLL_MAX_WAIT = 25
EDGE_COMMAND_TTL_SECONDS = {
    "identification": 10,
    "open_door": 30,
    "sync_now": 60,
    "enrollment_mode": 120,
    "reload": 60,
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.TenantJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "edge_node": "120/min",
        "kiosk": "120/min",
        "kiosk_lookup": "20/min",
        "kiosk_identify": "30/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sistema de Control y Registro de Acceso",
    "DESCRIPTION": (
        "API administrativa multi-tenant y protocolo Edge v1. La organización activa "
        "viaja en el claim org_id del JWT. El agente usa la API key del nodo. "
        "Los secretos de nodo, kiosco y Face-Auth solo se entregan al crearlos o regenerarlos. "
        "El contrato del agente está en docs/edge-protocol.md."
    ),
    "ENUM_NAME_OVERRIDES": {
        "CredentialTypeEnum": "apps.people.models.Credential.CredentialType",
        "EdgeCommandTypeEnum": "apps.sync.models.EdgeCommand.Type",
    },
    "TAGS": [
        {
            "name": "Protocolo Edge",
            "description": (
                "Contrato congelado v1 entre la nube y el agente. "
                "Cambios posteriores requieren ADR."
            ),
        }
    ],
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "SECURITY": [{"bearerAuth": []}],
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

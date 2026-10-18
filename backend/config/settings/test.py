from .base import *  # noqa: F403
from .base import MIDDLEWARE, REST_FRAMEWORK

DEBUG = False
ALLOW_DEMO_SEED = True
MIDDLEWARE = [item for item in MIDDLEWARE if "whitenoise" not in item]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {"edge_node": "10000/min"},
}

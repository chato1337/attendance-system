from django.urls import path

from apps.sync.consumers import EdgeConsumer
from apps.sync.panel import DashboardConsumer, KioskConsumer

websocket_urlpatterns = [
    path("ws/edge/", EdgeConsumer.as_asgi()),
    path("ws/dashboard/", DashboardConsumer.as_asgi()),
    path("ws/kiosk/", KioskConsumer.as_asgi()),
]

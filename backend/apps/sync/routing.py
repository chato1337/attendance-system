from django.urls import path

from apps.sync.consumers import EdgeConsumer

websocket_urlpatterns = [
    path("ws/edge/", EdgeConsumer.as_asgi()),
]

from django.conf import settings
from rest_framework import serializers

from apps.sync.models import EdgeCommand


class LogBatchSerializer(serializers.Serializer):
    node_id = serializers.UUIDField(required=False)
    logs = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate_logs(self, value):
        maximum = settings.EDGE_LOG_BATCH_MAX
        if len(value) > maximum:
            raise serializers.ValidationError(f"El lote admite como máximo {maximum} marcaciones.")
        return value


class HeartbeatSerializer(serializers.Serializer):
    agent_version = serializers.CharField(
        max_length=40,
        allow_blank=True,
        required=False,
        default="",
    )
    gateway_connected = serializers.BooleanField()
    listening_devices = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        default=list,
    )
    queue_size = serializers.IntegerField(min_value=0)
    last_version = serializers.IntegerField(min_value=0)
    commands_connected = serializers.BooleanField()
    gateway_version = serializers.CharField(
        max_length=40,
        allow_blank=True,
        required=False,
        default="",
    )


class AckSerializer(serializers.Serializer):
    result = serializers.DictField()


class DispatchCommandSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=EdgeCommand.Type.choices)
    payload = serializers.JSONField(required=False)
    wait = serializers.FloatField(required=False, min_value=0, max_value=30, default=0)

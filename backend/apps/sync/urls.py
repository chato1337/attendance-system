from django.urls import path

from apps.sync.views import (
    CommandAckView,
    CommandPollView,
    DeltaView,
    EnrollmentReadView,
    HeartbeatView,
    LogBatchView,
    NodeCommandDetailView,
    NodeCommandView,
)

urlpatterns = [
    path("edge/sync/delta/", DeltaView.as_view(), name="edge-delta"),
    path("edge/logs/batch/", LogBatchView.as_view(), name="edge-logs-batch"),
    path("edge/heartbeat/", HeartbeatView.as_view(), name="edge-heartbeat"),
    path("edge/commands/", CommandPollView.as_view(), name="edge-commands"),
    path("edge/enrollment-reads/", EnrollmentReadView.as_view(), name="edge-enrollment-reads"),
    path("edge/commands/<uuid:command_id>/ack/", CommandAckView.as_view(), name="edge-command-ack"),
    path("nodes/<uuid:node_id>/commands/", NodeCommandView.as_view(), name="node-commands"),
    path(
        "nodes/<uuid:node_id>/commands/<uuid:command_id>/",
        NodeCommandDetailView.as_view(),
        name="node-command-detail",
    ),
]

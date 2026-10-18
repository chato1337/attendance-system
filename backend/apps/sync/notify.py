import threading
from contextlib import contextmanager

_lock = threading.Lock()
_command_waiters: dict[str, set[threading.Event]] = {}
_ack_waiters: dict[str, set[threading.Event]] = {}


def _register(table: dict[str, set[threading.Event]], key: str) -> threading.Event:
    event = threading.Event()
    with _lock:
        table.setdefault(key, set()).add(event)
    return event


def _discard(table: dict[str, set[threading.Event]], key: str, event: threading.Event) -> None:
    with _lock:
        waiters = table.get(key)
        if not waiters:
            return
        waiters.discard(event)
        if not waiters:
            table.pop(key, None)


def _pulse(table: dict[str, set[threading.Event]], key: str) -> None:
    with _lock:
        waiters = list(table.get(key, ()))
    for event in waiters:
        event.set()


@contextmanager
def command_subscription(node_id):
    """Mantiene la suscripción durante todo el long-poll para no perder avisos."""

    key = str(node_id)
    event = _register(_command_waiters, key)
    try:
        yield event
    finally:
        _discard(_command_waiters, key, event)


def notify_commands(node_id) -> None:
    _pulse(_command_waiters, str(node_id))


def wait_for_ack(command_id, timeout: float) -> None:
    key = str(command_id)
    event = _register(_ack_waiters, key)
    try:
        event.wait(timeout)
    finally:
        _discard(_ack_waiters, key, event)


def notify_ack(command_id) -> None:
    _pulse(_ack_waiters, str(command_id))

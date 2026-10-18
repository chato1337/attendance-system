import importlib.util
import uuid
from pathlib import Path

from apps.access.models import AccessLog
from apps.people.models import Credential, Employee

SIMULATOR_PATH = (
    Path(__file__).resolve().parents[4] / "edge" / "tools" / "simulator" / "simulator.py"
)


def load_simulator():
    spec = importlib.util.spec_from_file_location("edge_simulator", SIMULATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class APIClientTransport:
    def __init__(self, client):
        self.client = client
        self.timeout = 30

    def request(self, method, path, body=None, timeout=None):
        handler = getattr(self.client, method.lower())
        kwargs = {}
        if body is not None:
            kwargs["data"] = body
            kwargs["format"] = "json"
        response = handler(path, **kwargs)
        return response.status_code, response.data


def test_simulator_pages_ten_thousand_credentials_and_deduplicates_logs(
    acme, acme_node, node_client
):
    employee = Employee.all_objects.create(
        organization=acme,
        document_id="SIM-1",
        first_name="Sim",
        last_name="Ulador",
    )
    Credential.all_objects.bulk_create(
        [
            Credential(
                organization=acme,
                employee=employee,
                type=Credential.CredentialType.RFID,
                payload=f"{index:010d}",
            )
            for index in range(10_000)
        ],
        batch_size=1000,
    )
    simulator = load_simulator().EdgeSimulator(APIClientTransport(node_client))
    pages = simulator.sync_all(limit=500)
    credentials = [row for page in pages for row in page["credentials"]]
    assert len(credentials) == 10_000
    assert pages[-1]["has_more"] is False
    assert simulator.version == pages[-1]["current_version"]

    logs = [
        {
            "id": str(uuid.uuid4()),
            "employee_id": str(employee.id),
            "timestamp": "2026-10-18T12:00:00Z",
            "direction": "IN" if index % 2 == 0 else "OUT",
            "status": "GRANTED",
            "method": "RFID",
            "source": "gateway",
        }
        for index in range(1000)
    ]
    logs.extend(logs[:25])
    first = simulator.push_logs(logs)
    assert sum(len(item["accepted"]) for item in first) == 1000
    assert sum(len(item["duplicated"]) for item in first) == 25
    second = simulator.push_logs(logs)
    assert sum(len(item["duplicated"]) for item in second) == 1025
    assert sum(len(item["accepted"]) for item in second) == 0
    assert AccessLog.all_objects.filter(node=acme_node).count() == 1000
    employee.refresh_from_db()
    assert employee.is_inside is False

    heartbeat = simulator.heartbeat(queue_size=1000, commands_connected=True)
    assert heartbeat["is_online"] is True
    page, acks = simulator.listen_once(wait=0)
    assert page["commands"] == []
    assert acks == []

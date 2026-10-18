"""Simulador del agente Edge para el protocolo v1.

Ejercita delta, lotes, heartbeat y el long-poll de comandos contra una API real.
No habla con el gateway: solo con la nube.

    python edge/tools/simulator/simulator.py --api-key <key> sync
    python edge/tools/simulator/simulator.py --api-key <key> listen --cycles 3
"""

import argparse
import json
import time
import urllib.error
import urllib.request


class SimulatorError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"{status}: {body}")


class UrllibTransport:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request(self, method: str, path: str, body=None, timeout=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.api_key}")
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return exc.code, parsed


class EdgeSimulator:
    def __init__(self, transport, batch_size: int = 500):
        self.transport = transport
        self.batch_size = batch_size
        self.version = 0

    def pull_delta(self, limit: int = 500) -> dict:
        page = self._ok(
            "GET",
            f"/api/v1/edge/sync/delta/?since_version={self.version}&limit={limit}",
        )
        previous = self.version
        self.version = page["next_since_version"]
        if page["has_more"] and self.version <= previous:
            raise SimulatorError(200, "el delta no avanzó el cursor")
        return page

    def sync_all(self, limit: int = 500, max_pages: int = 1000) -> list[dict]:
        pages = []
        for _ in range(max_pages):
            page = self.pull_delta(limit=limit)
            pages.append(page)
            if not page["has_more"]:
                return pages
        raise SimulatorError(200, "se superó el máximo de páginas del delta")

    def push_logs(self, logs: list[dict]) -> list[dict]:
        results = []
        size = self.batch_size
        for start in range(0, len(logs), size):
            chunk = logs[start : start + size]
            results.append(self._ok("POST", "/api/v1/edge/logs/batch/", {"logs": chunk}))
        return results

    def heartbeat(self, **fields) -> dict:
        body = {
            "agent_version": "simulator-0.1",
            "gateway_connected": True,
            "listening_devices": [],
            "queue_size": 0,
            "last_version": self.version,
            "commands_connected": False,
        }
        body.update(fields)
        return self._ok("POST", "/api/v1/edge/heartbeat/", body)

    def poll(self, wait: float = 0) -> dict:
        return self._ok(
            "GET",
            f"/api/v1/edge/commands/?wait={wait}",
            timeout=max(self.transport.timeout, wait + 5),
        )

    def ack(self, command_id: str, result: dict) -> dict:
        return self._ok("POST", f"/api/v1/edge/commands/{command_id}/ack/", {"result": result})

    def listen_once(self, wait: float = 0, handler=None):
        page = self.poll(wait=wait)
        acknowledgements = []
        for command in page["commands"]:
            if handler is None:
                result = {
                    "status": "GRANTED",
                    "door_opened": command["type"] in {"open_door", "identification"},
                }
            else:
                result = handler(command)
            acknowledgements.append(self.ack(command["id"], result))
        return page, acknowledgements

    def _ok(self, method: str, path: str, body=None, timeout=None):
        delay = 0.2
        last_error = None
        for attempt in range(3):
            try:
                status, payload = self.transport.request(method, path, body, timeout)
            except OSError as exc:
                last_error = exc
                if attempt == 2:
                    raise
                time.sleep(delay)
                delay *= 2
                continue
            if status == 429 and attempt < 2:
                time.sleep(delay)
                delay *= 2
                continue
            if status >= 400:
                raise SimulatorError(status, payload)
            return payload
        raise SimulatorError(0, last_error)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador del protocolo Edge v1")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--limit", type=int, default=500)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("sync")
    subcommands.add_parser("heartbeat")
    listen = subcommands.add_parser("listen")
    listen.add_argument("--wait", type=float, default=25)
    listen.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()
    simulator = EdgeSimulator(UrllibTransport(args.base_url, args.api_key))
    if args.command == "sync":
        pages = simulator.sync_all(limit=args.limit)
        totals = {key: sum(len(page[key]) for page in pages) for key in (
            "employees",
            "credentials",
            "reader_profiles",
            "doors",
            "readers",
        )}
        print(json.dumps({"version": simulator.version, "pages": len(pages), **totals}))
        return
    if args.command == "heartbeat":
        print(json.dumps(simulator.heartbeat()))
        return
    for _ in range(args.cycles):
        page, acks = simulator.listen_once(wait=args.wait)
        print(json.dumps({"commands": len(page["commands"]), "acks": [item["status"] for item in acks]}))


if __name__ == "__main__":
    main()

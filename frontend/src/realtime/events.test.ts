import { QueryClient } from "@tanstack/react-query";
import { describe, expect, test } from "vitest";

import type { AccessNode, LiveMessage, Page } from "@/api/types";

import { applyLiveMessage, dashboardSocketUrl, describeLive } from "./events";

const names = {
  employees: new Map([["emp-1", "Carlos Mendoza"]]),
  doors: new Map([["door-1", "Principal"]]),
  nodes: new Map([["node-1", "Norte"]]),
};

function message(event: string, data: Record<string, unknown>): LiveMessage {
  return {
    event,
    organization_id: "org-1",
    occurred_at: "2026-10-18T15:00:00Z",
    data,
  };
}

describe("tablero en vivo", () => {
  test("describe una marcación concedida y una denegada", () => {
    expect(
      describeLive(
        message("access.granted", {
          employee_id: "emp-1",
          door_id: "door-1",
          direction: "IN",
          method: "FACIAL",
        }),
        names,
      ),
    ).toBe("Ingreso · Carlos Mendoza · Principal · Rostro");
    expect(
      describeLive(
        message("access.denied", {
          employee_id: "emp-1",
          door_id: "door-1",
          method: "RFID",
          denial_reason: "APB_VIOLATION",
        }),
        names,
      ),
    ).toBe("Denegado · Carlos Mendoza · Principal · RFID · Anti-passback");
  });

  test("el socket del panel sale de la API y respeta un origen explícito", () => {
    expect(dashboardSocketUrl("http://localhost:8000/api/v1", "")).toBe(
      "ws://localhost:8001/ws/dashboard/",
    );
    expect(dashboardSocketUrl("http://localhost:8080/api/v1", "")).toBe(
      "ws://localhost:8080/ws/dashboard/",
    );
    expect(dashboardSocketUrl("http://localhost:8000/api/v1", "wss://panel.example")).toBe(
      "wss://panel.example/ws/dashboard/",
    );
  });

  test("funde el estado del nodo y el aforo en la caché", () => {
    const client = new QueryClient();
    const node: AccessNode = {
      id: "node-1",
      organization: "org-1",
      name: "Norte",
      site: "Planta",
      timezone: "UTC",
      is_active: true,
      is_online: false,
      last_heartbeat_at: null,
      last_sync_at: null,
      last_sync_version: 0,
      gateway_version_reported: "",
      agent_version: "",
      gateway_connected: false,
      listening_devices: [],
      queue_size: 4,
      commands_connected: false,
      api_key: null,
      deleted_at: null,
      created_at: "2026-10-18T12:00:00Z",
      updated_at: "2026-10-18T12:00:00Z",
    };
    const page: Page<AccessNode> = { count: 1, next: null, previous: null, results: [node] };
    client.setQueryData(["org-1", "/nodes/", "dashboard"], page);
    applyLiveMessage(
      client,
      "org-1",
      message("node.online", {
        node_id: "node-1",
        is_online: true,
        queue_size: 1,
        commands_connected: true,
        gateway_connected: true,
        agent_version: "0.3.0",
        last_heartbeat_at: "2026-10-18T15:04:00Z",
      }),
    );
    const updated = client.getQueryData<Page<AccessNode>>(["org-1", "/nodes/", "dashboard"]);
    expect(updated?.results[0].is_online).toBe(true);
    expect(updated?.results[0].queue_size).toBe(1);

    applyLiveMessage(
      client,
      "org-1",
      message("occupancy.changed", {
        total_inside: 2,
        sites: [],
        zones: [],
      }),
    );
    expect(client.getQueryData(["org-1", "/occupancy/"])).toMatchObject({ total_inside: 2 });
  });
});

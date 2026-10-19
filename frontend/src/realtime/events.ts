import type { QueryClient } from "@tanstack/react-query";

import { apiBaseUrl } from "@/api/client";
import type { AccessNode, LiveMessage, Occupancy, Page } from "@/api/types";
import { DENIAL_LABEL, DIRECTION_LABEL, METHOD_LABEL, labelOf } from "@/lib/labels";

export function dashboardSocketUrl(apiUrl = apiBaseUrl, configured = import.meta.env.VITE_WS_URL) {
  if (configured) {
    return `${configured.replace(/\/$/, "")}/ws/dashboard/`;
  }
  const api = new URL(apiUrl);
  const protocol = api.protocol === "https:" ? "wss:" : "ws:";
  const port = api.port === "8000" ? "8001" : api.port;
  const host = port ? `${api.hostname}:${port}` : api.hostname;
  return `${protocol}//${host}/ws/dashboard/`;
}

export function kioskSocketUrl(apiUrl = apiBaseUrl, configured = import.meta.env.VITE_WS_URL) {
  return dashboardSocketUrl(apiUrl, configured).replace(/\/ws\/dashboard\/$/, "/ws/kiosk/");
}

export function isOccupancy(value: unknown): value is Occupancy {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Occupancy;
  return typeof candidate.total_inside === "number" && Array.isArray(candidate.sites);
}

type Names = {
  employees: Map<string, string>;
  doors: Map<string, string>;
  nodes: Map<string, string>;
};

export function describeLive(message: LiveMessage, names: Names): string {
  const data = message.data;
  if (message.event === "access.granted" || message.event === "access.denied") {
    const who = names.employees.get(String(data.employee_id ?? "")) ?? "Sin empleado";
    const door = names.doors.get(String(data.door_id ?? "")) ?? "sin puerta";
    const method = labelOf(METHOD_LABEL, String(data.method ?? ""));
    if (message.event === "access.denied") {
      const reason = labelOf(DENIAL_LABEL, String(data.denial_reason ?? ""));
      return `Denegado · ${who} · ${door} · ${method} · ${reason}`;
    }
    const direction = labelOf(DIRECTION_LABEL, String(data.direction ?? ""));
    return `${direction} · ${who} · ${door} · ${method}`;
  }
  if (message.event === "node.online" || message.event === "node.offline") {
    const name = names.nodes.get(String(data.node_id ?? "")) ?? String(data.name ?? "Nodo");
    return message.event === "node.online" ? `${name} en línea` : `${name} sin conexión`;
  }
  if (message.event === "command.acked") {
    return `Comando ${String(data.type ?? "")} ${String(data.status ?? "")}`.trim();
  }
  if (message.event === "face.result") {
    return `Rostro · ${String(data.message || data.status || "resultado")}`;
  }
  if (message.event === "enrollment.read") {
    const payload = String(data.payload || data.raw || "");
    return payload ? `Lectura de enrolamiento · ${payload}` : "Lectura de enrolamiento";
  }
  return message.event;
}

export function applyLiveMessage(
  queryClient: QueryClient,
  organizationId: string,
  message: LiveMessage,
) {
  if (message.event === "occupancy.changed" && isOccupancy(message.data)) {
    queryClient.setQueryData([organizationId, "/occupancy/"], message.data);
    return;
  }
  if (message.event === "node.online" || message.event === "node.offline") {
    const nodeId = String(message.data.node_id ?? "");
    queryClient.setQueriesData<Page<AccessNode>>(
      { queryKey: [organizationId, "/nodes/"] },
      (current) => {
        if (!current?.results) {
          return current;
        }
        return {
          ...current,
          results: current.results.map((node) =>
            node.id === nodeId
              ? {
                  ...node,
                  is_online: Boolean(message.data.is_online),
                  queue_size: Number(message.data.queue_size ?? node.queue_size),
                  commands_connected: Boolean(message.data.commands_connected),
                  gateway_connected: Boolean(message.data.gateway_connected),
                  agent_version: String(message.data.agent_version ?? node.agent_version),
                  last_heartbeat_at:
                    typeof message.data.last_heartbeat_at === "string"
                      ? message.data.last_heartbeat_at
                      : node.last_heartbeat_at,
                }
              : node,
          ),
        };
      },
    );
    return;
  }
  if (message.event === "access.granted" || message.event === "access.denied") {
    void queryClient.invalidateQueries({ queryKey: [organizationId, "/access-logs/"] });
    return;
  }
  if (message.event === "enrollment.read") {
    void queryClient.invalidateQueries({ queryKey: [organizationId, "/enrollment-reads/"] });
    return;
  }
  if (message.event === "command.acked") {
    void queryClient.invalidateQueries({ queryKey: [organizationId, "/commands/"] });
  }
}

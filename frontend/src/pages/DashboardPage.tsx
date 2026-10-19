import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { AccessNode, Door, Employee, LiveMessage, Occupancy, Zone } from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { useSession } from "@/auth/session";
import { Badge, Button, Empty, Loading, Page } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { personName } from "@/lib/labels";
import { formatStamp } from "@/lib/time";
import { applyLiveMessage, describeLive, isOccupancy } from "@/realtime/events";
import { useDashboardStream, type StreamStatus } from "@/realtime/useDashboardStream";

const STATUS_LABEL: Record<StreamStatus, string> = {
  idle: "",
  offline: "Sin conexión",
  live: "En vivo",
  reconnecting: "Reconectando",
};

export function DashboardPage({ canReset }: { canReset: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const timeZone = usePreferences((state) => state.timeZone);
  const queryClient = useQueryClient();
  const [feed, setFeed] = useState<LiveMessage[]>([]);
  const [error, setError] = useState("");
  const occupancy = useOrgQuery(["/occupancy/"], () => api.get<Occupancy>("/occupancy/"));
  const nodes = useOrgQuery(["/nodes/", "dashboard"], () =>
    api.list<AccessNode>("/nodes/", { page_size: 100, ordering: "name" }),
  );
  const doors = useOrgQuery(["/doors/", "lookup"], () =>
    api.list<Door>("/doors/", { page_size: 100, ordering: "name" }),
  );
  const employees = useOrgQuery(["/employees/", "lookup"], () =>
    api.list<Employee>("/employees/", { page_size: 100, ordering: "last_name" }),
  );
  const zones = useOrgQuery(["/zones/", "lookup"], () =>
    api.list<Zone>("/zones/", { page_size: 100, ordering: "name" }),
  );

  const onEvent = useCallback(
    (message: LiveMessage) => {
      if (!organizationId || message.organization_id !== organizationId) {
        return;
      }
      if (message.event !== "occupancy.changed") {
        setFeed((current) => [message, ...current].slice(0, 40));
      }
      applyLiveMessage(queryClient, organizationId, message);
    },
    [organizationId, queryClient],
  );
  const status = useDashboardStream(onEvent);

  const snapshot = isOccupancy(occupancy.data) ? occupancy.data : null;
  const names = {
    nodes: new Map((nodes.data?.results ?? []).map((node) => [node.id, node.name])),
    doors: new Map((doors.data?.results ?? []).map((door) => [door.id, door.name])),
    employees: new Map(
      (employees.data?.results ?? []).map((employee) => [employee.id, personName(employee)]),
    ),
  };
  const denied = feed.filter((item) => item.event === "access.denied").slice(0, 5);

  async function resetSite(nodeId: string, name: string) {
    if (
      !window.confirm(
        `Los empleados que figuran dentro de «${name}» pasarán a estar fuera. El historial de marcaciones no se borra.`,
      )
    ) {
      return;
    }
    setError("");
    try {
      await api.create("/occupancy/reset/", { node: nodeId });
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/occupancy/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Tablero"
      lede="Aforo y marcaciones de la organización activa, a medida que llegan a la nube."
      actions={
        status === "idle" ? null : (
          <Badge tone={status === "live" ? "ok" : status === "reconnecting" ? "warn" : "off"}>
            {STATUS_LABEL[status]}
          </Badge>
        )
      }
    >
      {error ? <p className="banner">{error}</p> : null}
      {occupancy.isLoading ? <Loading /> : null}
      {snapshot ? (
        <>
          <div className="stats">
            <article>
              <span>Dentro ahora</span>
              <strong>{snapshot.total_inside}</strong>
            </article>
            <article>
              <span>Sedes</span>
              <strong>{snapshot.sites.length}</strong>
            </article>
            <article>
              <span>Zonas</span>
              <strong>{zones.data?.results.length ?? snapshot.zones.length}</strong>
            </article>
          </div>
          <div className="dashboard">
            <section className="card">
              <h2>Por sede y zona</h2>
              <table className="grid">
                <thead>
                  <tr>
                    <th>Sede</th>
                    <th>Dentro</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.sites.map((site) => (
                    <tr key={site.node_id ?? "none"}>
                      <td>
                        {site.name}
                        {site.site ? <small>{site.site}</small> : null}
                      </td>
                      <td>{site.inside}</td>
                      <td>
                        {canReset && site.node_id && site.inside > 0 ? (
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => {
                              if (site.node_id) {
                                void resetSite(site.node_id, site.name);
                              }
                            }}
                          >
                            Reiniciar
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3>Zonas</h3>
              {snapshot.zones.length === 0 ? (
                <Empty>No hay zonas con personas dentro.</Empty>
              ) : (
                <ul className="choice-list">
                  {snapshot.zones.map((zone) => (
                    <li key={zone.zone_id ?? "none"}>
                      <span>{zone.name}</span>
                      <strong>{zone.inside}</strong>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="stack">
              <div className="card">
                <h2>Nodos</h2>
                {(nodes.data?.results ?? []).length === 0 ? (
                  <Empty>No hay nodos en esta organización.</Empty>
                ) : (
                  <ul className="choice-list">
                    {nodes.data?.results.map((node) => (
                      <li key={node.id}>
                        <span>
                          {node.name}
                          <small>
                            {node.site || "Sin sede"} · cola {node.queue_size}
                            {node.commands_connected ? " · comandos" : ""}
                          </small>
                        </span>
                        <Badge tone={node.is_online ? "ok" : "off"}>
                          {node.is_online ? "En línea" : "Fuera"}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              {denied.length > 0 ? (
                <div className="card">
                  <h2>Denegados recientes</h2>
                  <ul className="feed">
                    {denied.map((item, index) => (
                      <li key={`${item.occurred_at}-${index}`} className="denied">
                        <time>{formatStamp(item.occurred_at, timeZone)}</time>
                        <span>{describeLive(item, names)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          </div>
        </>
      ) : occupancy.isLoading ? null : (
        <Empty>El aforo todavía no está disponible.</Empty>
      )}
      <section className="card feed-card">
        <h2>Flujo en vivo</h2>
        {feed.length === 0 ? (
          <Empty>Las marcaciones aparecen aquí en cuanto la nube las recibe.</Empty>
        ) : (
          <ul className="feed">
            {feed.map((item, index) => (
              <li
                key={`${item.occurred_at}-${item.event}-${index}`}
                className={item.event === "access.denied" ? "denied" : undefined}
              >
                <time>{formatStamp(item.occurred_at, timeZone)}</time>
                <span>{describeLive(item, names)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Page>
  );
}

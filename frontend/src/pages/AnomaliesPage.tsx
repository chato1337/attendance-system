import { useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { AccessAnomaly, AccessNode, Employee } from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { Empty, Field, Loading, Page, Pager } from "@/components/ui";
import { ANOMALY_LABEL, labelOf, personName } from "@/lib/labels";
import { formatStamp } from "@/lib/time";

function summary(anomaly: AccessAnomaly): string {
  if (anomaly.kind === "APB_CONFLICT") {
    return anomaly.detail.resolution === "kept_newer"
      ? "Se conservó la marcación más reciente."
      : "El empate se resolvió por orden de llegada.";
  }
  if (anomaly.kind === "STATE_RESET") {
    return "Un operador reinició el estado de presencia.";
  }
  if (anomaly.kind === "OCCUPANCY_DRIFT") {
    return "El recálculo corrigió el estado guardado.";
  }
  return "El nodo reportó una violación de anti-passback.";
}

export function AnomaliesPage() {
  const timeZone = usePreferences((state) => state.timeZone);
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState("");
  const anomalies = useOrgQuery(["/access-anomalies/", page, kind], () =>
    api.list<AccessAnomaly>("/access-anomalies/", {
      page,
      page_size: 20,
      ordering: "-created_at",
      kind,
    }),
  );
  const nodes = useOrgQuery(["/nodes/", "lookup"], () =>
    api.list<AccessNode>("/nodes/", { page_size: 100, ordering: "name" }),
  );
  const employees = useOrgQuery(["/employees/", "lookup"], () =>
    api.list<Employee>("/employees/", { page_size: 100, ordering: "last_name" }),
  );
  const nodeName = new Map((nodes.data?.results ?? []).map((node) => [node.id, node.name]));
  const employeeName = new Map(
    (employees.data?.results ?? []).map((employee) => [employee.id, personName(employee)]),
  );
  const rows = anomalies.data?.results ?? [];

  return (
    <Page
      title="Anomalías"
      lede="Conflictos de presencia entre nodos, anti-passback reportado y correcciones de aforo."
    >
      <div className="filters">
        <Field label="Tipo">
          <select
            value={kind}
            onChange={(event) => {
              setPage(1);
              setKind(event.target.value);
            }}
          >
            <option value="">Todos</option>
            {Object.entries(ANOMALY_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {anomalies.isLoading ? <Loading /> : null}
      {!anomalies.isLoading && rows.length === 0 ? (
        <Empty>No hay anomalías con ese filtro.</Empty>
      ) : null}
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>Cuando</th>
                <th>Tipo</th>
                <th>Empleado</th>
                <th>Nodo</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((anomaly) => (
                <tr key={anomaly.id}>
                  <td>{formatStamp(anomaly.created_at, timeZone)}</td>
                  <td>{labelOf(ANOMALY_LABEL, anomaly.kind)}</td>
                  <td>{anomaly.employee ? (employeeName.get(anomaly.employee) ?? "—") : "—"}</td>
                  <td>{anomaly.node ? (nodeName.get(anomaly.node) ?? "—") : "—"}</td>
                  <td>{summary(anomaly)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Pager page={page} count={anomalies.data?.count ?? 0} pageSize={20} onPage={setPage} />
    </Page>
  );
}

import { useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { AccessLog, AccessNode, Door, Employee } from "@/api/types";
import { emptyLogFilters, usePreferences } from "@/auth/preferences";
import { Banner, Button, Empty, Field, Loading, Page, Pager } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import {
  DENIAL_LABEL,
  DIRECTION_LABEL,
  METHOD_LABEL,
  SOURCE_LABEL,
  STATUS_LABEL,
  labelOf,
  personName,
} from "@/lib/labels";
import { endOfDayIso, formatStamp, startOfDayIso } from "@/lib/time";

export function LogsPage() {
  const timeZone = usePreferences((state) => state.timeZone);
  const filters = usePreferences((state) => state.logFilters);
  const setFilters = usePreferences((state) => state.setLogFilters);
  const [page, setPage] = useState(1);
  const nodes = useOrgQuery(["/nodes/", "lookup"], () =>
    api.list<AccessNode>("/nodes/", { page_size: 100, ordering: "name" }),
  );
  const doors = useOrgQuery(["/doors/", "lookup"], () =>
    api.list<Door>("/doors/", { page_size: 100, ordering: "name" }),
  );
  const employees = useOrgQuery(["/employees/", "lookup"], () =>
    api.list<Employee>("/employees/", { page_size: 100, ordering: "last_name" }),
  );
  const logs = useOrgQuery(["/access-logs/", page, filters], () =>
    api.list<AccessLog>("/access-logs/", {
      page,
      page_size: 20,
      ordering: "-timestamp",
      node: filters.node,
      door: filters.door,
      employee: filters.employee,
      status: filters.status,
      denial_reason: filters.denial_reason,
      method: filters.method,
      source: filters.source,
      timestamp_after: startOfDayIso(filters.timestamp_after, timeZone),
      timestamp_before: endOfDayIso(filters.timestamp_before, timeZone),
    }),
  );

  const nodeName = new Map((nodes.data?.results ?? []).map((node) => [node.id, node.name]));
  const doorName = new Map((doors.data?.results ?? []).map((door) => [door.id, door.name]));
  const employeeName = new Map(
    (employees.data?.results ?? []).map((employee) => [employee.id, personName(employee)]),
  );

  function update(partial: Partial<typeof filters>) {
    setPage(1);
    setFilters({ ...filters, ...partial });
  }

  return (
    <Page
      title="Marcaciones"
      lede="Historial que ya llegó a la nube. Las horas se muestran en la zona de preferencias."
    >
      <div className="filters">
        <Field label="Desde">
          <input
            type="date"
            value={filters.timestamp_after}
            onChange={(event) => update({ timestamp_after: event.target.value })}
          />
        </Field>
        <Field label="Hasta">
          <input
            type="date"
            value={filters.timestamp_before}
            onChange={(event) => update({ timestamp_before: event.target.value })}
          />
        </Field>
        <Field label="Nodo">
          <select value={filters.node} onChange={(event) => update({ node: event.target.value })}>
            <option value="">Todos</option>
            {nodes.data?.results.map((node) => (
              <option key={node.id} value={node.id}>
                {node.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Puerta">
          <select value={filters.door} onChange={(event) => update({ door: event.target.value })}>
            <option value="">Todas</option>
            {doors.data?.results.map((door) => (
              <option key={door.id} value={door.id}>
                {door.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Empleado">
          <select
            value={filters.employee}
            onChange={(event) => update({ employee: event.target.value })}
          >
            <option value="">Todos</option>
            {employees.data?.results.map((employee) => (
              <option key={employee.id} value={employee.id}>
                {personName(employee)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Estado">
          <select
            value={filters.status}
            onChange={(event) => update({ status: event.target.value })}
          >
            <option value="">Todos</option>
            {Object.entries(STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Motivo">
          <select
            value={filters.denial_reason}
            onChange={(event) => update({ denial_reason: event.target.value })}
          >
            <option value="">Todos</option>
            {Object.entries(DENIAL_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Método">
          <select
            value={filters.method}
            onChange={(event) => update({ method: event.target.value })}
          >
            <option value="">Todos</option>
            {Object.entries(METHOD_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Origen">
          <select
            value={filters.source}
            onChange={(event) => update({ source: event.target.value })}
          >
            <option value="">Todos</option>
            {Object.entries(SOURCE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Button type="button" variant="ghost" onClick={() => setFilters(emptyLogFilters)}>
          Limpiar filtros
        </Button>
      </div>
      {logs.isLoading ? <Loading /> : null}
      {logs.isError ? <Banner>{errorMessage(logs.error)}</Banner> : null}
      {(logs.data?.results.length ?? 0) === 0 && !logs.isLoading ? (
        <Empty>No hay marcaciones con esos filtros.</Empty>
      ) : null}
      {(logs.data?.results.length ?? 0) > 0 ? (
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Marcaciones</caption>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Empleado</th>
                <th>Puerta</th>
                <th>Nodo</th>
                <th>Estado</th>
                <th>Método</th>
                <th>Origen</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {logs.data?.results.map((log) => (
                <tr key={log.id}>
                  <td>{formatStamp(log.timestamp, timeZone)}</td>
                  <td>{log.employee ? (employeeName.get(log.employee) ?? "—") : "—"}</td>
                  <td>
                    {log.door ? (doorName.get(log.door) ?? "—") : "—"}
                    <small>{labelOf(DIRECTION_LABEL, log.direction)}</small>
                  </td>
                  <td>{log.node ? (nodeName.get(log.node) ?? "—") : "—"}</td>
                  <td>{labelOf(STATUS_LABEL, log.status)}</td>
                  <td>{labelOf(METHOD_LABEL, log.method)}</td>
                  <td>{labelOf(SOURCE_LABEL, log.source)}</td>
                  <td>{labelOf(DENIAL_LABEL, log.denial_reason)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Pager page={page} count={logs.data?.count ?? 0} pageSize={20} onPage={setPage} />
    </Page>
  );
}

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type {
  AccessNode,
  AttendanceSummary,
  DailyAttendance,
  Department,
  ExportFormat,
  ExportJob,
} from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { useSession } from "@/auth/session";
import { Badge, Banner, Button, Empty, Field, Loading, Page, Pager } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { ATTENDANCE_LABEL, labelOf } from "@/lib/labels";
import { formatStamp } from "@/lib/time";

const FORMATS: { id: ExportFormat; label: string }[] = [
  { id: "csv", label: "CSV" },
  { id: "xlsx", label: "Excel" },
  { id: "pdf", label: "PDF" },
  { id: "json", label: "JSON" },
];

function dayStamp(date: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatMinutes(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours} h ${rest.toString().padStart(2, "0")} min`;
}

function percent(rate: number | null): string {
  if (rate === null) {
    return "—";
  }
  return `${Math.round(rate * 1000) / 10} %`;
}

export function ReportsPage({ canRecalculate }: { canRecalculate: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const timeZone = usePreferences((state) => state.timeZone);
  const queryClient = useQueryClient();
  const today = dayStamp(new Date(), timeZone);
  const weekAgo = dayStamp(new Date(Date.now() - 6 * 24 * 60 * 60 * 1000), timeZone);
  const [dateFrom, setDateFrom] = useState(weekAgo);
  const [dateTo, setDateTo] = useState(today);
  const [department, setDepartment] = useState("");
  const [site, setSite] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const downloaded = useRef("");

  const filters = {
    date_from: dateFrom,
    date_to: dateTo,
    department,
    site,
    status,
  };
  const summary = useOrgQuery(["/reports/summary/", filters], () =>
    api.get<AttendanceSummary>("/reports/summary/", filters),
  );
  const rows = useOrgQuery(["/reports/attendance/", page, filters], () =>
    api.list<DailyAttendance>("/reports/attendance/", {
      page,
      page_size: 20,
      ordering: "-work_date",
      ...filters,
    }),
  );
  const departments = useOrgQuery(["/departments/", "lookup"], () =>
    api.list<Department>("/departments/", { page_size: 100, ordering: "name" }),
  );
  const nodes = useOrgQuery(["/nodes/", "lookup"], () =>
    api.list<AccessNode>("/nodes/", { page_size: 100, ordering: "name" }),
  );
  const job = useOrgQuery(
    ["/reports/exports/", jobId],
    () => api.get<ExportJob>(`/reports/exports/${jobId}/`),
    {
      enabled: Boolean(jobId),
      refetchInterval: (query) => {
        const current = query.state.data?.status;
        return current === "PENDING" || current === "RUNNING" ? 1500 : false;
      },
    },
  );

  useEffect(() => {
    const ready = job.data;
    if (!ready || ready.status !== "READY" || !ready.download_url || downloaded.current === ready.id) {
      return;
    }
    downloaded.current = ready.id;
    const from = ready.filters.date_from ?? dateFrom;
    const to = ready.filters.date_to ?? dateTo;
    void api.download(ready.download_url, `asistencia-${from}-${to}.${ready.format}`);
  }, [job.data, dateFrom, dateTo]);

  const sites = [
    ...new Set((nodes.data?.results ?? []).map((node) => node.site).filter(Boolean)),
  ];
  const snapshot = summary.data;
  const maxMinutes = Math.max(...(snapshot?.by_department.map((item) => item.worked_minutes) ?? [0]), 1);
  const maxPeople = Math.max(
    ...(snapshot?.by_day.map((item) => item.present + item.absent) ?? [0]),
    1,
  );

  async function recalculate() {
    setError("");
    setBusy(true);
    try {
      await api.create("/reports/recalculate/", { date_from: dateFrom, date_to: dateTo });
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/reports/summary/"] });
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/reports/attendance/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function exportReport(format: ExportFormat) {
    setError("");
    try {
      const created = await api.create<ExportJob>("/reports/exports/", {
        format,
        date_from: dateFrom,
        date_to: dateTo,
        department: department || null,
        site,
        status,
      });
      downloaded.current = "";
      setJobId(created.id);
      if (created.status === "READY" && created.download_url) {
        downloaded.current = created.id;
        await api.download(
          created.download_url,
          `asistencia-${dateFrom}-${dateTo}.${created.format}`,
        );
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Reportes"
      lede="Permanencia, puntualidad y ausencias según el horario de la organización. El cálculo corre aparte de la descarga."
      actions={
        canRecalculate ? (
          <Button type="button" onClick={() => void recalculate()} disabled={busy}>
            {busy ? "Calculando…" : "Calcular período"}
          </Button>
        ) : null
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      <div className="filters">
        <Field label="Desde">
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => {
              setPage(1);
              setDateFrom(event.target.value);
            }}
          />
        </Field>
        <Field label="Hasta">
          <input
            type="date"
            value={dateTo}
            onChange={(event) => {
              setPage(1);
              setDateTo(event.target.value);
            }}
          />
        </Field>
        <Field label="Departamento">
          <select
            value={department}
            onChange={(event) => {
              setPage(1);
              setDepartment(event.target.value);
            }}
          >
            <option value="">Todos</option>
            {departments.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Sede">
          <select
            value={site}
            onChange={(event) => {
              setPage(1);
              setSite(event.target.value);
            }}
          >
            <option value="">Todas</option>
            {sites.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Estado">
          <select
            value={status}
            onChange={(event) => {
              setPage(1);
              setStatus(event.target.value);
            }}
          >
            <option value="">Todos</option>
            {Object.entries(ATTENDANCE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {summary.isLoading ? <Loading /> : null}
      {summary.isError ? <Banner>{errorMessage(summary.error)}</Banner> : null}
      {snapshot ? (
        <>
          <div className="stats">
            <article>
              <span>Horas trabajadas</span>
              <strong>{formatMinutes(snapshot.worked_minutes)}</strong>
            </article>
            <article>
              <span>Puntualidad</span>
              <strong>{percent(snapshot.punctuality_rate)}</strong>
            </article>
            <article>
              <span>Ausentismo</span>
              <strong>{percent(snapshot.absenteeism_rate)}</strong>
            </article>
            <article>
              <span>Tardanzas</span>
              <strong>{snapshot.late_days}</strong>
            </article>
            <article>
              <span>Salidas anticipadas</span>
              <strong>{snapshot.early_leave_days}</strong>
            </article>
            <article>
              <span>Marcas huérfanas</span>
              <strong>{snapshot.incomplete_days}</strong>
            </article>
          </div>
          <div className="dashboard">
            <section className="card">
              <h2>Horas por departamento</h2>
              {snapshot.by_department.length === 0 ? (
                <Empty>No hay filas en este período. Calcule para generarlas.</Empty>
              ) : (
                <div className="bars">
                  {snapshot.by_department.map((item) => (
                    <div className="bar-row" key={item.department_id ?? "none"}>
                      <span>{item.name}</span>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{ width: `${(item.worked_minutes / maxMinutes) * 100}%` }}
                        />
                      </div>
                      <span>{formatMinutes(item.worked_minutes)}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
            <section className="card">
              <h2>Tendencia diaria</h2>
              <div className="trend" aria-label="Presentes y ausentes por día">
                {snapshot.by_day.map((item) => (
                  <div className="trend-col" key={item.date} title={item.date}>
                    <div className="trend-stack">
                      <i
                        className="trend-present"
                        style={{ height: `${(item.present / maxPeople) * 100}%` }}
                      />
                      <i
                        className="trend-absent"
                        style={{ height: `${(item.absent / maxPeople) * 100}%` }}
                      />
                    </div>
                    <small>{item.date.slice(8)}</small>
                  </div>
                ))}
              </div>
              <p className="hint">Verde: días cerrados con ingreso. Rojo: ausencias.</p>
            </section>
          </div>
        </>
      ) : null}

      <section className="card">
        <header className="page-head">
          <h2>Detalle</h2>
          <div className="page-actions">
            {FORMATS.map((format) => (
              <Button
                key={format.id}
                variant="ghost"
                type="button"
                onClick={() => void exportReport(format.id)}
              >
                {format.label}
              </Button>
            ))}
          </div>
        </header>
        {job.data?.status === "PENDING" || job.data?.status === "RUNNING" ? (
          <Banner tone="info">Generando el archivo. La descarga empieza al terminar.</Banner>
        ) : null}
        {job.data?.status === "FAILED" ? <Banner>{job.data.error}</Banner> : null}
        {rows.isLoading ? <Loading /> : null}
        {(rows.data?.results.length ?? 0) === 0 && !rows.isLoading ? (
          <Empty>Sin asistencia calculada para estos filtros.</Empty>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Empleado</th>
                <th>Departamento</th>
                <th>Sede</th>
                <th>Estado</th>
                <th>Permanencia</th>
                <th>Entrada</th>
                <th>Salida</th>
              </tr>
            </thead>
            <tbody>
              {rows.data?.results.map((row) => (
                <tr key={row.id}>
                  <td>{row.work_date}</td>
                  <td>
                    {row.employee_name}
                    <small>{row.document_id}</small>
                  </td>
                  <td>{row.department_name}</td>
                  <td>{row.site || "—"}</td>
                  <td>
                    <Badge tone={row.status === "ABSENT" || row.status === "INCOMPLETE" ? "warn" : "ok"}>
                      {labelOf(ATTENDANCE_LABEL, row.status)}
                    </Badge>
                  </td>
                  <td>
                    {formatMinutes(row.worked_minutes)}
                    {row.late_minutes > 0 ? <small>{row.late_minutes} min tarde</small> : null}
                    {row.early_leave_minutes > 0 ? (
                      <small>{row.early_leave_minutes} min antes</small>
                    ) : null}
                  </td>
                  <td>{formatStamp(row.first_in, timeZone)}</td>
                  <td>{formatStamp(row.last_out, timeZone)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Pager
          page={page}
          count={rows.data?.count ?? 0}
          pageSize={20}
          onPage={setPage}
        />
      </section>
    </Page>
  );
}

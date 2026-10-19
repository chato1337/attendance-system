import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type {
  FaceEnrollmentSession,
  FaceIntegration,
  FaceMetrics,
  FaceReadiness,
} from "@/api/types";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Page } from "@/components/ui";
import { canAdminister } from "@/lib/access";
import { errorMessage } from "@/lib/errors";
import { personName } from "@/lib/labels";

const IDENTIFICATION: Record<string, string> = {
  PENDING: "Pendientes",
  REJECTED: "Rechazadas",
  UNKNOWN_FACE: "Rostro desconocido",
  GRANTED: "Concedidas",
  DENIED: "Denegadas",
  NODE_UNREACHABLE: "Nodo sin respuesta",
};

const SESSION_STATUS: Record<string, string> = {
  PENDING: "Pendiente",
  COMPLETED: "Completada",
  FAILED: "Fallida",
  REJECTED: "Rechazada",
  EXPIRED: "Vencida",
};

const ISSUE: Record<string, string> = {
  missing_email: "Sin correo",
  invalid_email: "Correo inválido",
  duplicate_email: "Correo duplicado",
};

export function FacePage() {
  const organizationId = useSession((state) => state.organizationId);
  const role = useSession((state) => state.role);
  const admin = canAdminister(role);
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [apiKey, setApiKey] = useState("");
  const integration = useOrgQuery(
    ["/faceauth-integration/"],
    () => api.get<FaceIntegration>("/faceauth-integration/"),
    { enabled: admin },
  );
  const readiness = useOrgQuery(["/employees/face-readiness/"], () =>
    api.get<{ count: number; results: FaceReadiness[] }>("/employees/face-readiness/"),
  );
  const sessions = useOrgQuery(["/face-enrollment-sessions/"], () =>
    api.list<FaceEnrollmentSession>("/face-enrollment-sessions/", {
      page_size: 20,
      ordering: "-created_at",
    }),
  );
  const metrics = useOrgQuery(["/faceauth-integration/metrics/"], () =>
    api.get<FaceMetrics>("/faceauth-integration/metrics/"),
  );
  const current = integration.data;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!current) {
      return;
    }
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      app_id: String(form.get("app_id") ?? ""),
      api_url: String(form.get("api_url") ?? ""),
      server_api_url: String(form.get("server_api_url") ?? ""),
      web_url: String(form.get("web_url") ?? ""),
      enabled: form.get("enabled") === "on",
      allow_panel_login: form.get("allow_panel_login") === "on",
      allow_kiosk_self_enrollment: form.get("allow_kiosk_self_enrollment") === "on",
    };
    if (apiKey.trim()) {
      body.api_key = apiKey.trim();
    }
    try {
      await api.update("/faceauth-integration/", body);
      setApiKey("");
      setNotice("Configuración guardada.");
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/faceauth-integration/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function testConnection() {
    setError("");
    setNotice("");
    try {
      const result = await api.create<{ ok: boolean; name?: string; detail?: string }>(
        "/faceauth-integration/test/",
      );
      setNotice(
        result.ok ? `Conexión correcta${result.name ? `: ${result.name}` : ""}.` : "Sin conexión.",
      );
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Rostro"
      lede="Face-Auth identifica a la persona. Esta instalación solo guarda el identificador, nunca el video."
    >
      {error ? <Banner>{error}</Banner> : null}
      {notice ? <Banner tone="ok">{notice}</Banner> : null}
      {metrics.isError ? <Banner>{errorMessage(metrics.error)}</Banner> : null}
      {sessions.isError ? <Banner>{errorMessage(sessions.error)}</Banner> : null}
      {readiness.isError ? <Banner>{errorMessage(readiness.error)}</Banner> : null}
      {integration.isLoading ? <Loading /> : null}
      {current && admin ? (
        <form className="form-grid card" onSubmit={(event) => void save(event)}>
          <Field label="App ID">
            <input name="app_id" defaultValue={current.app_id} />
          </Field>
          <Field label="API key">
            <input
              type="password"
              value={apiKey}
              autoComplete="new-password"
              placeholder={
                current.api_key_set
                  ? "Guardada. Escriba otra solo para rotarla."
                  : "Obligatoria para habilitar"
              }
              onChange={(event) => setApiKey(event.target.value)}
            />
          </Field>
          <Field label="URL para el navegador">
            <input name="api_url" defaultValue={current.api_url} />
          </Field>
          <Field label="URL para la nube">
            <input
              name="server_api_url"
              defaultValue={current.server_api_url}
              placeholder="Igual que la del navegador si coinciden"
            />
          </Field>
          <Field label="URL del sitio Face-Auth">
            <input name="web_url" defaultValue={current.web_url} />
          </Field>
          <label className="check">
            <input type="checkbox" name="enabled" defaultChecked={current.enabled} />
            Habilitado
          </label>
          <label className="check">
            <input
              type="checkbox"
              name="allow_panel_login"
              defaultChecked={current.allow_panel_login}
            />
            Permitir ingreso al panel con rostro
          </label>
          <label className="check">
            <input
              type="checkbox"
              name="allow_kiosk_self_enrollment"
              defaultChecked={current.allow_kiosk_self_enrollment}
            />
            Permitir que el kiosco registre el rostro
          </label>
          <div className="page-actions">
            <Button type="submit">Guardar</Button>
            <Button type="button" variant="ghost" onClick={() => void testConnection()}>
              Probar conexión
            </Button>
          </div>
          <div>
            <h3>Orígenes CORS</h3>
            <ul>
              {current.cors_origins.map((origin) => (
                <li key={origin}>
                  <code>{origin}</code>
                </li>
              ))}
            </ul>
            <h3>Callbacks del flujo alojado</h3>
            <ul>
              {current.hosted_redirect_uris.map((uri) => (
                <li key={uri}>
                  <code>{uri}</code>
                </li>
              ))}
            </ul>
          </div>
        </form>
      ) : null}
      <section className="stack">
        <h2>Últimas 24 horas</h2>
        {metrics.isLoading ? <Loading /> : null}
        {metrics.data ? (
          <ul className="metrics">
            <li>
              Verificación p95:{" "}
              {metrics.data.verify_ms_p95 == null
                ? "sin muestras"
                : `${metrics.data.verify_ms_p95} ms`}
            </li>
            <li>Bajas pendientes en Face-Auth: {metrics.data.pending_deletions}</li>
            {Object.entries(metrics.data.identifications).map(([status, count]) => (
              <li key={status}>
                {IDENTIFICATION[status] ?? status}: {count}
              </li>
            ))}
            {Object.entries(metrics.data.codes).map(([code, count]) => (
              <li key={code}>
                {code}: {count}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      <section className="stack">
        <h2>Sesiones de enrolamiento</h2>
        {sessions.isLoading ? <Loading /> : null}
        {(sessions.data?.results.length ?? 0) === 0 && !sessions.isLoading ? (
          <Empty>Todavía no hay sesiones.</Empty>
        ) : null}
        {(sessions.data?.results.length ?? 0) > 0 ? (
          <div className="table-wrap">
            <table className="grid">
              <caption className="sr-only">Sesiones de enrolamiento facial</caption>
              <thead>
                <tr>
                  <th>Empleado</th>
                  <th>Origen</th>
                  <th>Estado</th>
                  <th>Código</th>
                </tr>
              </thead>
              <tbody>
                {sessions.data?.results.map((row) => (
                  <tr key={row.id}>
                    <td>{row.employee_name}</td>
                    <td>{row.started_by === "KIOSK" ? "Kiosco" : "Panel"}</td>
                    <td>{SESSION_STATUS[row.status] ?? row.status}</td>
                    <td>{row.failure_code || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
      <section className="stack">
        <h2>Preparación</h2>
        {readiness.isLoading ? <Loading /> : null}
        {(readiness.data?.results.length ?? 0) === 0 && !readiness.isLoading ? (
          <Empty>Todos los empleados pueden enrolar el rostro.</Empty>
        ) : null}
        {(readiness.data?.results.length ?? 0) > 0 ? (
          <div className="table-wrap">
            <table className="grid">
              <caption className="sr-only">Empleados que no pueden enrolar el rostro</caption>
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>Nombre</th>
                  <th>Problema</th>
                </tr>
              </thead>
              <tbody>
                {readiness.data?.results.map((row) => (
                  <tr key={row.id}>
                    <td>{row.document_id}</td>
                    <td>{personName(row)}</td>
                    <td>{row.issues.map((issue) => ISSUE[issue] ?? issue).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </Page>
  );
}

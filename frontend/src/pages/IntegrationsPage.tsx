import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { APIToken, WebhookDelivery, WebhookSubscription } from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Modal, Page, SecretReveal } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { WEBHOOK_EVENT_LABEL, WEBHOOK_STATUS_LABEL, labelOf } from "@/lib/labels";
import { formatStamp } from "@/lib/time";

const EVENT_OPTIONS = [
  "access.granted",
  "access.denied",
  "device.status_changed",
  "employee.updated",
  "occupancy.threshold",
  "face.enrolled",
] as const;

const SCOPE_OPTIONS = ["employees:read", "employees:write", "webhooks:manage"] as const;

export function IntegrationsPage({ canEdit }: { canEdit: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const timeZone = usePreferences((state) => state.timeZone);
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [tokenValue, setTokenValue] = useState<string | null>(null);
  const [selectedWebhook, setSelectedWebhook] = useState<string>("");
  const [hookForm, setHookForm] = useState({
    name: "",
    url: "",
    events: ["access.granted", "access.denied"] as string[],
  });
  const [tokenForm, setTokenForm] = useState({
    name: "",
    scopes: ["employees:read"] as string[],
  });

  const webhooks = useOrgQuery(["/webhooks/"], () =>
    api.list<WebhookSubscription>("/webhooks/", { page_size: 100, ordering: "name" }),
  );
  const tokens = useOrgQuery(["/api-tokens/"], () =>
    api.list<APIToken>("/api-tokens/", { page_size: 100, ordering: "-created_at" }),
  );
  const deliveries = useOrgQuery(
    ["/webhooks/", selectedWebhook, "deliveries"],
    () =>
      api.list<WebhookDelivery>(`/webhooks/${selectedWebhook}/deliveries/`, {
        page_size: 20,
        ordering: "-created_at",
      }),
    { enabled: Boolean(selectedWebhook) },
  );

  async function refresh(path: string) {
    await queryClient.invalidateQueries({ queryKey: [organizationId, path] });
  }

  async function createWebhook() {
    setError("");
    try {
      const created = await api.create<WebhookSubscription>("/webhooks/", {
        name: hookForm.name,
        url: hookForm.url,
        events: hookForm.events,
        is_active: true,
      });
      if (created.secret_value) {
        setSecret(created.secret_value);
      }
      setHookForm({ name: "", url: "", events: ["access.granted", "access.denied"] });
      setSelectedWebhook(created.id);
      await refresh("/webhooks/");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function deactivateWebhook(id: string) {
    setError("");
    try {
      await api.remove(`/webhooks/${id}/`);
      if (selectedWebhook === id) {
        setSelectedWebhook("");
      }
      await refresh("/webhooks/");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function sendTest(id: string) {
    setError("");
    try {
      await api.create(`/webhooks/${id}/test/`, { event: "access.granted" });
      setSelectedWebhook(id);
      await queryClient.invalidateQueries({
        queryKey: [organizationId, "/webhooks/", id, "deliveries"],
      });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function resend(id: string) {
    setError("");
    try {
      await api.create(`/webhook-deliveries/${id}/resend/`);
      if (selectedWebhook) {
        await queryClient.invalidateQueries({
          queryKey: [organizationId, "/webhooks/", selectedWebhook, "deliveries"],
        });
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function createToken() {
    setError("");
    try {
      const created = await api.create<APIToken>("/api-tokens/", {
        name: tokenForm.name,
        scopes: tokenForm.scopes,
        is_active: true,
      });
      if (created.token) {
        setTokenValue(created.token);
      }
      setTokenForm({ name: "", scopes: ["employees:read"] });
      await refresh("/api-tokens/");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function revokeToken(id: string) {
    setError("");
    try {
      await api.remove(`/api-tokens/${id}/`);
      await refresh("/api-tokens/");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  return (
    <Page
      title="Integraciones"
      lede="Webhooks firmados hacia su ERP y tokens de API con alcances por organización."
    >
      {error ? <Banner>{error}</Banner> : null}
      {secret ? (
        <Modal title="Secreto del webhook" onClose={() => setSecret(null)}>
          <SecretReveal
            title="Guarde este secreto"
            secret={secret}
            hint="Cópielo ahora. No se volverá a mostrar."
          />
          <Button type="button" onClick={() => setSecret(null)}>
            Entendido
          </Button>
        </Modal>
      ) : null}
      {tokenValue ? (
        <Modal title="Token de API" onClose={() => setTokenValue(null)}>
          <SecretReveal
            title="Guarde este token"
            secret={tokenValue}
            hint="Cópielo ahora. No se volverá a mostrar."
          />
          <Button type="button" onClick={() => setTokenValue(null)}>
            Entendido
          </Button>
        </Modal>
      ) : null}

      <section className="card">
        <header className="page-head">
          <h2>Webhooks</h2>
        </header>
        {canEdit ? (
          <div className="filters">
            <Field label="Nombre">
              <input
                value={hookForm.name}
                onChange={(event) => setHookForm({ ...hookForm, name: event.target.value })}
              />
            </Field>
            <Field label="URL">
              <input
                value={hookForm.url}
                onChange={(event) => setHookForm({ ...hookForm, url: event.target.value })}
                placeholder="https://…"
              />
            </Field>
            <Field label="Eventos">
              <div className="checks">
                {EVENT_OPTIONS.map((event) => (
                  <label key={event}>
                    <input
                      type="checkbox"
                      checked={hookForm.events.includes(event)}
                      onChange={() =>
                        setHookForm({ ...hookForm, events: toggle(hookForm.events, event) })
                      }
                    />
                    {labelOf(WEBHOOK_EVENT_LABEL, event)}
                  </label>
                ))}
              </div>
            </Field>
            <Button type="button" onClick={() => void createWebhook()}>
              Crear suscripción
            </Button>
          </div>
        ) : null}
        {webhooks.isLoading ? <Loading /> : null}
        {(webhooks.data?.results.length ?? 0) === 0 ? (
          <Empty>Sin suscripciones.</Empty>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>URL</th>
                <th>Eventos</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {webhooks.data?.results.map((hook) => (
                <tr key={hook.id}>
                  <td>{hook.name}</td>
                  <td>
                    <small>{hook.url}</small>
                  </td>
                  <td>
                    <small>{hook.events.map((event) => labelOf(WEBHOOK_EVENT_LABEL, event)).join(", ")}</small>
                  </td>
                  <td>{hook.is_active ? "Activa" : "Inactiva"}</td>
                  <td className="row-actions">
                    <Button variant="ghost" type="button" onClick={() => setSelectedWebhook(hook.id)}>
                      Entregas
                    </Button>
                    {canEdit ? (
                      <>
                        <Button variant="ghost" type="button" onClick={() => void sendTest(hook.id)}>
                          Probar
                        </Button>
                        <Button
                          variant="ghost"
                          type="button"
                          onClick={() => void deactivateWebhook(hook.id)}
                        >
                          Desactivar
                        </Button>
                      </>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {selectedWebhook ? (
          <div className="stack">
            <h3>Entregas recientes</h3>
            {deliveries.isLoading ? <Loading /> : null}
            {(deliveries.data?.results.length ?? 0) === 0 ? (
              <Empty>Aún no hay entregas.</Empty>
            ) : (
              <table className="grid">
                <thead>
                  <tr>
                    <th>Evento</th>
                    <th>Estado</th>
                    <th>Intentos</th>
                    <th>HTTP</th>
                    <th>Creada</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {deliveries.data?.results.map((delivery) => (
                    <tr key={delivery.id}>
                      <td>{labelOf(WEBHOOK_EVENT_LABEL, delivery.event)}</td>
                      <td>{labelOf(WEBHOOK_STATUS_LABEL, delivery.status)}</td>
                      <td>{delivery.attempt}</td>
                      <td>{delivery.response_status ?? "—"}</td>
                      <td>{formatStamp(delivery.created_at, timeZone)}</td>
                      <td>
                        {canEdit ? (
                          <Button
                            variant="ghost"
                            type="button"
                            onClick={() => void resend(delivery.id)}
                          >
                            Reenviar
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ) : null}
      </section>

      <section className="card">
        <header className="page-head">
          <h2>Tokens de API</h2>
        </header>
        {canEdit ? (
          <div className="filters">
            <Field label="Nombre">
              <input
                value={tokenForm.name}
                onChange={(event) => setTokenForm({ ...tokenForm, name: event.target.value })}
              />
            </Field>
            <Field label="Alcances">
              <div className="checks">
                {SCOPE_OPTIONS.map((scope) => (
                  <label key={scope}>
                    <input
                      type="checkbox"
                      checked={tokenForm.scopes.includes(scope)}
                      onChange={() =>
                        setTokenForm({ ...tokenForm, scopes: toggle(tokenForm.scopes, scope) })
                      }
                    />
                    {scope}
                  </label>
                ))}
              </div>
            </Field>
            <Button type="button" onClick={() => void createToken()}>
              Crear token
            </Button>
          </div>
        ) : null}
        {tokens.isLoading ? <Loading /> : null}
        {(tokens.data?.results.length ?? 0) === 0 ? (
          <Empty>Sin tokens.</Empty>
        ) : (
          <table className="grid">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Prefijo</th>
                <th>Alcances</th>
                <th>Último uso</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tokens.data?.results.map((token) => (
                <tr key={token.id}>
                  <td>{token.name}</td>
                  <td>
                    <code>{token.token_prefix}…</code>
                  </td>
                  <td>
                    <small>{token.scopes.join(", ")}</small>
                  </td>
                  <td>{formatStamp(token.last_used_at, timeZone)}</td>
                  <td>
                    {canEdit && token.is_active ? (
                      <Button variant="ghost" type="button" onClick={() => void revokeToken(token.id)}>
                        Revocar
                      </Button>
                    ) : (
                      "Revocado"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </Page>
  );
}

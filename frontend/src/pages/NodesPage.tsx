import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { AccessNode } from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { useSession } from "@/auth/session";
import {
  Badge,
  Banner,
  Button,
  Empty,
  Field,
  Loading,
  Modal,
  Page,
  SecretReveal,
} from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { formatAgo, formatStamp, zoneOptions } from "@/lib/time";

const schema = z.object({
  name: z.string().trim().min(1, "Indique el nombre."),
  site: z.string(),
  timezone: z.string().min(1, "Elija una zona horaria."),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

export function NodesPage({ canEdit }: { canEdit: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const timeZone = usePreferences((state) => state.timeZone);
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<AccessNode | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState("");
  const nodes = useOrgQuery(
    ["/nodes/", "status"],
    () => api.list<AccessNode>("/nodes/", { page_size: 100, ordering: "name" }),
    { refetchInterval: 15000 },
  );
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", site: "", timezone: timeZone, is_active: true },
  });

  const rows = nodes.data?.results ?? [];
  const online = rows.filter((node) => node.is_online).length;
  const queue = rows.reduce((sum, node) => sum + node.queue_size, 0);

  function openCreate() {
    setEditing(null);
    form.reset({ name: "", site: "", timezone: timeZone, is_active: true });
    setCreating(true);
  }

  function openEdit(node: AccessNode) {
    setEditing(node);
    form.reset({
      name: node.name,
      site: node.site,
      timezone: node.timezone,
      is_active: node.is_active,
    });
    setCreating(true);
  }

  async function onSubmit(values: FormValues) {
    setError("");
    try {
      const saved = editing
        ? await api.update<AccessNode>(`/nodes/${editing.id}/`, values)
        : await api.create<AccessNode>("/nodes/", values);
      if (saved.api_key) {
        setSecret(saved.api_key);
      }
      setCreating(false);
      setEditing(null);
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/nodes/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function regenerate(node: AccessNode) {
    if (!window.confirm(`La llave actual de «${node.name}» dejará de funcionar.`)) {
      return;
    }
    setError("");
    try {
      const saved = await api.create<AccessNode>(`/nodes/${node.id}/regenerate-key/`);
      if (saved.api_key) {
        setSecret(saved.api_key);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function deactivate(node: AccessNode) {
    if (!window.confirm(`${node.is_active ? "Desactivar" : "Reactivar"} «${node.name}»?`)) {
      return;
    }
    setError("");
    try {
      if (node.is_active) {
        await api.remove(`/nodes/${node.id}/`);
      } else {
        await api.update(`/nodes/${node.id}/`, { is_active: true });
      }
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/nodes/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Nodos"
      lede="Estado que reporta el latido de cada sede: conexión, cola y canal de comandos."
      actions={
        canEdit ? (
          <Button type="button" onClick={openCreate}>
            Nuevo nodo
          </Button>
        ) : null
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      <div className="stats">
        <article>
          <span>En línea</span>
          <strong>{online}</strong>
        </article>
        <article>
          <span>Sin conexión</span>
          <strong>{rows.length - online}</strong>
        </article>
        <article>
          <span>Marcaciones en cola</span>
          <strong>{queue}</strong>
        </article>
      </div>
      {nodes.isLoading ? <Loading /> : null}
      {nodes.isError ? <Banner>{errorMessage(nodes.error)}</Banner> : null}
      {rows.length === 0 && !nodes.isLoading ? <Empty>Todavía no hay nodos.</Empty> : null}
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Estado de nodos</caption>
            <thead>
              <tr>
                <th>Nodo</th>
                <th>Estado</th>
                <th>Latido</th>
                <th>Agente</th>
                <th>Cola</th>
                <th>Gateway</th>
                <th>Comandos</th>
                {canEdit ? <th>Acciones</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((node) => (
                <tr key={node.id}>
                  <td>
                    <strong>{node.name}</strong>
                    <small>{node.site || "Sin sede"}</small>
                  </td>
                  <td>
                    <Badge tone={node.is_online ? "ok" : "off"}>
                      {node.is_online ? "En línea" : "Sin conexión"}
                    </Badge>
                    {node.is_active ? null : <Badge tone="warn">Inactivo</Badge>}
                  </td>
                  <td>
                    {formatAgo(node.last_heartbeat_at)}
                    <small>{formatStamp(node.last_heartbeat_at, timeZone)}</small>
                  </td>
                  <td>
                    {node.agent_version || "—"}
                    <small>sync v{node.last_sync_version}</small>
                  </td>
                  <td>{node.queue_size}</td>
                  <td>
                    <Badge tone={node.gateway_connected ? "ok" : "off"}>
                      {node.gateway_connected ? "Conectado" : "Sin gateway"}
                    </Badge>
                    <small>{node.gateway_version_reported || "versión no reportada"}</small>
                  </td>
                  <td>
                    <Badge tone={node.commands_connected ? "ok" : "warn"}>
                      {node.commands_connected ? "Canal activo" : "Canal inactivo"}
                    </Badge>
                  </td>
                  {canEdit ? (
                    <td className="row-actions">
                      <button type="button" onClick={() => openEdit(node)}>
                        Editar
                      </button>
                      <button type="button" onClick={() => void regenerate(node)}>
                        Nueva llave
                      </button>
                      <button type="button" onClick={() => void deactivate(node)}>
                        {node.is_active ? "Desactivar" : "Reactivar"}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {creating ? (
        <Modal title={editing ? "Editar nodo" : "Nuevo nodo"} onClose={() => setCreating(false)}>
          <form className="form-grid" onSubmit={form.handleSubmit(onSubmit)}>
            <Field label="Nombre" error={form.formState.errors.name?.message}>
              <input {...form.register("name")} />
            </Field>
            <Field label="Sede">
              <input {...form.register("site")} />
            </Field>
            <Field label="Zona horaria">
              <select {...form.register("timezone")}>
                {zoneOptions(form.watch("timezone")).map((zone) => (
                  <option key={zone} value={zone}>
                    {zone}
                  </option>
                ))}
              </select>
            </Field>
            <label className="check">
              <input type="checkbox" {...form.register("is_active")} />
              Activo
            </label>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              Guardar nodo
            </Button>
          </form>
        </Modal>
      ) : null}
      {secret ? (
        <Modal title="Llave del nodo" onClose={() => setSecret(null)}>
          <SecretReveal
            title="Copie la llave en agent.yaml"
            secret={secret}
            hint="Esta llave no vuelve a mostrarse. Si se pierde, genere una nueva."
          />
          <Button type="button" onClick={() => setSecret(null)}>
            Entendido
          </Button>
        </Modal>
      ) : null}
    </Page>
  );
}

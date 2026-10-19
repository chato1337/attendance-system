import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Page } from "@/api/types";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Page as PageView, Pager } from "@/components/ui";
import { errorMessage } from "@/lib/errors";

const schema = z.object({
  name: z.string().trim().min(1, "Indique el nombre."),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof schema>;
type Named = { id: string; name: string; is_active: boolean };

export function CatalogPage({
  title,
  lede,
  path,
  canEdit,
}: {
  title: string;
  lede: string;
  path: string;
  canEdit: boolean;
}) {
  const organizationId = useSession((state) => state.organizationId);
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Named | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const query = useOrgQuery([path, page], () =>
    api.list<Named>(path, { page, page_size: 20, ordering: "name" }),
  );
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", is_active: true },
  });

  function openCreate() {
    setEditing(null);
    setCreating(true);
    form.reset({ name: "", is_active: true });
  }

  function openEdit(row: Named) {
    setCreating(false);
    setEditing(row);
    form.reset({ name: row.name, is_active: row.is_active });
  }

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: [organizationId, path] });
  }

  async function onSubmit(values: FormValues) {
    setError("");
    try {
      if (editing) {
        await api.update(`${path}${editing.id}/`, values);
      } else {
        await api.create(path, values);
      }
      setCreating(false);
      setEditing(null);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function deactivate(row: Named) {
    const verb = row.is_active ? "Desactivar" : "Reactivar";
    if (!window.confirm(`${verb} «${row.name}»?`)) {
      return;
    }
    setError("");
    try {
      if (row.is_active) {
        await api.remove(`${path}${row.id}/`);
      } else {
        await api.update(`${path}${row.id}/`, { is_active: true });
      }
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const rows = (query.data as Page<Named> | undefined)?.results ?? [];
  const showForm = creating || editing;

  return (
    <PageView
      title={title}
      lede={lede}
      actions={
        canEdit ? (
          <Button type="button" onClick={openCreate}>
            Nuevo
          </Button>
        ) : null
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      {query.isLoading ? <Loading /> : null}
      {query.isError ? <Banner>{errorMessage(query.error)}</Banner> : null}
      {showForm && canEdit ? (
        <form className="form-grid card" onSubmit={form.handleSubmit(onSubmit)}>
          <Field label="Nombre" error={form.formState.errors.name?.message}>
            <input {...form.register("name")} />
          </Field>
          <label className="check">
            <input type="checkbox" {...form.register("is_active")} />
            Activo
          </label>
          <div className="form-actions">
            <Button type="submit" disabled={form.formState.isSubmitting}>
              Guardar
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setCreating(false);
                setEditing(null);
              }}
            >
              Cancelar
            </Button>
          </div>
        </form>
      ) : null}
      {rows.length === 0 && !query.isLoading ? <Empty>No hay registros.</Empty> : null}
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Estado</th>
                {canEdit ? <th>Acciones</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td>{row.is_active ? "Activo" : "Inactivo"}</td>
                  {canEdit ? (
                    <td className="row-actions">
                      <button type="button" onClick={() => openEdit(row)}>
                        Editar
                      </button>
                      <button type="button" onClick={() => void deactivate(row)}>
                        {row.is_active ? "Desactivar" : "Reactivar"}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Pager page={page} count={query.data?.count ?? 0} pageSize={20} onPage={setPage} />
    </PageView>
  );
}

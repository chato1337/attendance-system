import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Door, Kiosk } from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Modal, Page, SecretReveal } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { formatStamp } from "@/lib/time";

const schema = z.object({
  name: z.string().trim().min(1, "Indique el nombre."),
  door: z.string().min(1, "Elija la puerta."),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

export function KiosksPage({ canEdit }: { canEdit: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const timeZone = usePreferences((state) => state.timeZone);
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Kiosk | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState("");
  const kiosks = useOrgQuery(["/kiosks/"], () =>
    api.list<Kiosk>("/kiosks/", { page_size: 100, ordering: "name" }),
  );
  const doors = useOrgQuery(["/doors/", "lookup"], () =>
    api.list<Door>("/doors/", { page_size: 100, ordering: "name" }),
  );
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", door: "", is_active: true },
  });
  const doorName = new Map((doors.data?.results ?? []).map((door) => [door.id, door.name]));

  function startCreate() {
    setEditing(null);
    form.reset({ name: "", door: "", is_active: true });
    setOpen(true);
  }

  function startEdit(kiosk: Kiosk) {
    setEditing(kiosk);
    form.reset({ name: kiosk.name, door: kiosk.door, is_active: kiosk.is_active });
    setOpen(true);
  }

  async function onSubmit(values: FormValues) {
    setError("");
    try {
      const saved = editing
        ? await api.update<Kiosk>(`/kiosks/${editing.id}/`, values)
        : await api.create<Kiosk>("/kiosks/", values);
      if (saved.kiosk_token) {
        setSecret(saved.kiosk_token);
      }
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/kiosks/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function regenerate(kiosk: Kiosk) {
    if (!window.confirm(`El token actual de «${kiosk.name}» dejará de funcionar.`)) {
      return;
    }
    setError("");
    try {
      const saved = await api.create<Kiosk>(`/kiosks/${kiosk.id}/regenerate-token/`);
      if (saved.kiosk_token) {
        setSecret(saved.kiosk_token);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function deactivate(kiosk: Kiosk) {
    setError("");
    try {
      if (kiosk.is_active) {
        await api.remove(`/kiosks/${kiosk.id}/`);
      } else {
        await api.update(`/kiosks/${kiosk.id}/`, { is_active: true });
      }
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/kiosks/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Kioscos"
      lede="Cada kiosco queda asociado a una puerta. El token se muestra una sola vez."
      actions={
        canEdit ? (
          <Button type="button" onClick={startCreate}>
            Nuevo kiosco
          </Button>
        ) : null
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      {kiosks.isLoading ? <Loading /> : null}
      {(kiosks.data?.results.length ?? 0) === 0 && !kiosks.isLoading ? (
        <Empty>No hay kioscos.</Empty>
      ) : null}
      {(kiosks.data?.results.length ?? 0) > 0 ? (
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Kioscos</caption>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Puerta</th>
                <th>Última vez</th>
                <th>Estado</th>
                {canEdit ? <th>Acciones</th> : null}
              </tr>
            </thead>
            <tbody>
              {kiosks.data?.results.map((kiosk) => (
                <tr key={kiosk.id}>
                  <td>{kiosk.name}</td>
                  <td>{doorName.get(kiosk.door) ?? "—"}</td>
                  <td>{formatStamp(kiosk.last_seen_at, timeZone)}</td>
                  <td>{kiosk.is_active ? "Activo" : "Inactivo"}</td>
                  {canEdit ? (
                    <td className="row-actions">
                      <button type="button" onClick={() => startEdit(kiosk)}>
                        Editar
                      </button>
                      <button type="button" onClick={() => void regenerate(kiosk)}>
                        Nuevo token
                      </button>
                      <button type="button" onClick={() => void deactivate(kiosk)}>
                        {kiosk.is_active ? "Desactivar" : "Reactivar"}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {open ? (
        <Modal title={editing ? "Editar kiosco" : "Nuevo kiosco"} onClose={() => setOpen(false)}>
          <form className="form-grid" onSubmit={form.handleSubmit(onSubmit)}>
            <Field label="Nombre" error={form.formState.errors.name?.message}>
              <input {...form.register("name")} />
            </Field>
            <Field label="Puerta" error={form.formState.errors.door?.message}>
              <select {...form.register("door")}>
                <option value="">Elegir</option>
                {doors.data?.results.map((door) => (
                  <option key={door.id} value={door.id}>
                    {door.name}
                  </option>
                ))}
              </select>
            </Field>
            <label className="check">
              <input type="checkbox" {...form.register("is_active")} />
              Activo
            </label>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              Guardar kiosco
            </Button>
          </form>
        </Modal>
      ) : null}
      {secret ? (
        <Modal title="Token del kiosco" onClose={() => setSecret(null)}>
          <SecretReveal
            title="Péguelo una vez en el kiosco"
            secret={secret}
            hint="Este token no vuelve a mostrarse. La pantalla del kiosco llega en la fase de Face-Auth."
          />
          <Button type="button" onClick={() => setSecret(null)}>
            Entendido
          </Button>
        </Modal>
      ) : null}
    </Page>
  );
}

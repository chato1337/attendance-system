import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { AccessNode, Door, EdgeCommand, Reader, ReaderProfile, Zone } from "@/api/types";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Page } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { APB_LABEL, COMMAND_STATUS_LABEL, DIRECTION_LABEL } from "@/lib/labels";

const doorSchema = z.object({
  name: z.string().trim().min(1, "Indique el nombre."),
  node: z.string().min(1, "Elija el nodo."),
  zone: z.string(),
  relay_device_id: z.string().trim().min(1, "Indique el relé."),
  direction: z.enum(["IN", "OUT"]),
  apb_mode: z.enum(["OFF", "SOFT", "HARD"]),
  face_enabled: z.boolean(),
  is_active: z.boolean(),
});

const readerSchema = z.object({
  name: z.string().trim().min(1, "Indique el nombre."),
  reader_device_id: z.string().trim().min(1, "Indique el device_id."),
  reader_profile: z.string().min(1, "Elija el perfil."),
  is_active: z.boolean(),
});

const openSchema = z.object({
  reason: z.string().trim().min(1, "Indique el motivo."),
});

type DoorForm = z.infer<typeof doorSchema>;
type ReaderForm = z.infer<typeof readerSchema>;

export function DoorsPage({ canEdit, canOpen }: { canEdit: boolean; canOpen: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const username = useSession((state) => state.user?.username ?? "");
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [command, setCommand] = useState<EdgeCommand | null>(null);

  const doors = useOrgQuery(["/doors/"], () =>
    api.list<Door>("/doors/", { page_size: 100, ordering: "name" }),
  );
  const nodes = useOrgQuery(["/nodes/", "lookup"], () =>
    api.list<AccessNode>("/nodes/", { page_size: 100, ordering: "name" }),
  );
  const zones = useOrgQuery(["/zones/", "lookup"], () =>
    api.list<Zone>("/zones/", { page_size: 100, ordering: "name", is_active: true }),
  );
  const profiles = useOrgQuery(["/reader-profiles/", "lookup"], () =>
    api.list<ReaderProfile>("/reader-profiles/", { page_size: 100, is_active: true }),
  );
  const readers = useOrgQuery(
    ["/readers/", selectedId ?? ""],
    () => api.list<Reader>("/readers/", { door: selectedId, page_size: 100 }),
    { enabled: Boolean(selectedId) },
  );

  const selected = doors.data?.results.find((door) => door.id === selectedId) ?? null;
  const nodeName = new Map((nodes.data?.results ?? []).map((node) => [node.id, node.name]));
  const zoneName = new Map((zones.data?.results ?? []).map((zone) => [zone.id, zone.name]));
  const profileName = new Map(
    (profiles.data?.results ?? []).map((profile) => [profile.id, profile.name]),
  );

  const doorForm = useForm<DoorForm>({
    resolver: zodResolver(doorSchema),
    defaultValues: {
      name: "",
      node: "",
      zone: "",
      relay_device_id: "",
      direction: "IN",
      apb_mode: "OFF",
      face_enabled: false,
      is_active: true,
    },
  });
  const readerForm = useForm<ReaderForm>({
    resolver: zodResolver(readerSchema),
    defaultValues: { name: "", reader_device_id: "", reader_profile: "", is_active: true },
  });
  const openForm = useForm<{ reason: string }>({
    resolver: zodResolver(openSchema),
    defaultValues: { reason: "" },
  });

  function editDoor(door: Door) {
    setSelectedId(door.id);
    setCreating(false);
    setCommand(null);
    doorForm.reset({
      name: door.name,
      node: door.node,
      zone: door.zone ?? "",
      relay_device_id: door.relay_device_id,
      direction: door.direction,
      apb_mode: door.apb_mode,
      face_enabled: door.face_enabled,
      is_active: door.is_active,
    });
  }

  async function saveDoor(values: DoorForm) {
    setError("");
    const body = {
      ...values,
      zone: values.zone || null,
      required_factors: selected?.required_factors ?? [],
    };
    try {
      const saved = selected
        ? await api.update<Door>(`/doors/${selected.id}/`, body)
        : await api.create<Door>("/doors/", body);
      setSelectedId(saved.id);
      setCreating(false);
      editDoor(saved);
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/doors/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function saveReader(values: ReaderForm) {
    if (!selected) {
      return;
    }
    setError("");
    try {
      await api.create("/readers/", { ...values, door: selected.id });
      readerForm.reset({ name: "", reader_device_id: "", reader_profile: "", is_active: true });
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/readers/", selected.id] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function deactivateReader(reader: Reader) {
    setError("");
    try {
      if (reader.is_active) {
        await api.remove(`/readers/${reader.id}/`);
      } else {
        await api.update(`/readers/${reader.id}/`, { is_active: true });
      }
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/readers/", selectedId] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function openDoor(values: { reason: string }) {
    if (!selected) {
      return;
    }
    setError("");
    setCommand(null);
    try {
      const result = await api.create<EdgeCommand>(`/nodes/${selected.node}/commands/`, {
        type: "open_door",
        payload: { door_id: selected.id, reason: values.reason, actor: username },
        wait: 8,
      });
      setCommand(result);
      openForm.reset({ reason: "" });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Puertas"
      lede="Cada puerta pertenece a un nodo, apunta a un relé y puede tener varios lectores."
      actions={
        canEdit ? (
          <Button
            type="button"
            onClick={() => {
              setSelectedId(null);
              setCreating(true);
              setCommand(null);
              doorForm.reset({
                name: "",
                node: nodes.data?.results[0]?.id ?? "",
                zone: "",
                relay_device_id: "",
                direction: "IN",
                apb_mode: "OFF",
                face_enabled: false,
                is_active: true,
              });
            }}
          >
            Nueva puerta
          </Button>
        ) : null
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      {doors.isLoading ? <Loading /> : null}
      <div className="split">
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Puertas</caption>
            <thead>
              <tr>
                <th>Puerta</th>
                <th>Nodo</th>
                <th>Dirección</th>
                <th>APB</th>
              </tr>
            </thead>
            <tbody>
              {doors.data?.results.map((door) => (
                <tr key={door.id} className={door.id === selectedId ? "selected" : ""}>
                  <td>
                    <button type="button" className="linkish" onClick={() => editDoor(door)}>
                      {door.name}
                    </button>
                  </td>
                  <td>{nodeName.get(door.node) ?? "—"}</td>
                  <td>{DIRECTION_LABEL[door.direction]}</td>
                  <td>{APB_LABEL[door.apb_mode]}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(doors.data?.results.length ?? 0) === 0 && !doors.isLoading ? (
            <Empty>No hay puertas.</Empty>
          ) : null}
        </div>
        {creating || selected ? (
          <aside className="detail card">
            <h2>{selected ? selected.name : "Nueva puerta"}</h2>
            {canEdit ? (
              <form className="form-grid" onSubmit={doorForm.handleSubmit(saveDoor)}>
                <Field label="Nombre" error={doorForm.formState.errors.name?.message}>
                  <input {...doorForm.register("name")} />
                </Field>
                <Field label="Nodo" error={doorForm.formState.errors.node?.message}>
                  <select {...doorForm.register("node")}>
                    <option value="">Elegir</option>
                    {nodes.data?.results.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Zona">
                  <select {...doorForm.register("zone")}>
                    <option value="">Sin zona</option>
                    {zones.data?.results.map((zone) => (
                      <option key={zone.id} value={zone.id}>
                        {zone.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field
                  label="Relé (device_id)"
                  error={doorForm.formState.errors.relay_device_id?.message}
                >
                  <input {...doorForm.register("relay_device_id")} />
                </Field>
                <Field label="Dirección">
                  <select {...doorForm.register("direction")}>
                    <option value="IN">Ingreso</option>
                    <option value="OUT">Salida</option>
                  </select>
                </Field>
                <Field label="Anti-passback">
                  <select {...doorForm.register("apb_mode")}>
                    <option value="OFF">Apagado</option>
                    <option value="SOFT">Blando</option>
                    <option value="HARD">Duro</option>
                  </select>
                </Field>
                <label className="check">
                  <input type="checkbox" {...doorForm.register("face_enabled")} />
                  Acepta identificación facial
                </label>
                <label className="check">
                  <input type="checkbox" {...doorForm.register("is_active")} />
                  Activa
                </label>
                <Button type="submit" disabled={doorForm.formState.isSubmitting}>
                  Guardar puerta
                </Button>
              </form>
            ) : (
              <p>
                {selected ? zoneName.get(selected.zone ?? "") : ""} · relé{" "}
                {selected?.relay_device_id}
              </p>
            )}
            {selected && canOpen ? (
              <form className="form-grid" onSubmit={openForm.handleSubmit(openDoor)}>
                <h3>Apertura remota</h3>
                <Field label="Motivo" error={openForm.formState.errors.reason?.message}>
                  <input {...openForm.register("reason")} />
                </Field>
                <Button type="submit" disabled={openForm.formState.isSubmitting}>
                  Abrir puerta
                </Button>
                {command ? (
                  <Banner tone={command.status === "ACKED" ? "ok" : "info"}>
                    Comando {COMMAND_STATUS_LABEL[command.status] ?? command.status}
                    {command.result ? ` · ${JSON.stringify(command.result)}` : ""}
                  </Banner>
                ) : null}
              </form>
            ) : null}
            {selected ? (
              <div>
                <h3>Lectores</h3>
                <ul className="credential-list">
                  {readers.data?.results.map((reader) => (
                    <li key={reader.id}>
                      <div>
                        <strong>{reader.name}</strong>
                        <code>{reader.reader_device_id}</code>
                        <small>
                          {profileName.get(reader.reader_profile) ?? "perfil"}
                          {reader.is_active ? "" : " · inactivo"}
                        </small>
                      </div>
                      {canEdit ? (
                        <button type="button" onClick={() => void deactivateReader(reader)}>
                          {reader.is_active ? "Desactivar" : "Reactivar"}
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
                {readers.isError ? <Banner>{errorMessage(readers.error)}</Banner> : null}
                {(readers.data?.results.length ?? 0) === 0 && !readers.isError ? (
                  <Empty>Sin lectores.</Empty>
                ) : null}
                {canEdit ? (
                  <form className="form-grid" onSubmit={readerForm.handleSubmit(saveReader)}>
                    <Field
                      label="Nombre del lector"
                      error={readerForm.formState.errors.name?.message}
                    >
                      <input {...readerForm.register("name")} />
                    </Field>
                    <Field
                      label="Puerto o device_id"
                      error={readerForm.formState.errors.reader_device_id?.message}
                    >
                      <input {...readerForm.register("reader_device_id")} />
                    </Field>
                    <Field
                      label="Perfil"
                      error={readerForm.formState.errors.reader_profile?.message}
                    >
                      <select {...readerForm.register("reader_profile")}>
                        <option value="">Elegir</option>
                        {profiles.data?.results.map((profile) => (
                          <option key={profile.id} value={profile.id}>
                            {profile.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Button type="submit">Agregar lector</Button>
                  </form>
                ) : null}
              </div>
            ) : null}
          </aside>
        ) : (
          <aside className="detail card">
            <Empty>Seleccione una puerta.</Empty>
          </aside>
        )}
      </div>
    </Page>
  );
}

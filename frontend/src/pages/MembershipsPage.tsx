import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Membership } from "@/api/types";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Modal, Page } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { ROLE_LABEL } from "@/lib/labels";

const schema = z.object({
  username: z.string().trim().min(1, "Indique el usuario."),
  email: z.string().trim().email("Correo inválido."),
  password: z.string().min(8, "Use al menos 8 caracteres."),
  first_name: z.string(),
  last_name: z.string(),
  role: z.enum(["ADMIN", "OPERATOR", "VIEWER"]),
});

const roleSchema = z.object({
  role: z.enum(["ADMIN", "OPERATOR", "VIEWER"]),
});

type FormValues = z.infer<typeof schema>;

export function MembershipsPage({ canEdit }: { canEdit: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Membership | null>(null);
  const [error, setError] = useState("");
  const memberships = useOrgQuery(["/memberships/"], () =>
    api.list<Membership>("/memberships/", { page_size: 100, ordering: "user__username" }),
  );
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      username: "",
      email: "",
      password: "",
      first_name: "",
      last_name: "",
      role: "OPERATOR",
    },
  });
  const roleForm = useForm<{ role: Membership["role"] }>({
    resolver: zodResolver(roleSchema),
    defaultValues: { role: "OPERATOR" },
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: [organizationId, "/memberships/"] });
  }

  async function createMember(values: FormValues) {
    setError("");
    try {
      await api.create("/memberships/", values);
      setCreating(false);
      form.reset();
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function saveRole(values: { role: Membership["role"] }) {
    if (!editing) {
      return;
    }
    setError("");
    try {
      await api.update(`/memberships/${editing.id}/`, { role: values.role });
      setEditing(null);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function remove(member: Membership) {
    if (!window.confirm(`Quitar a ${member.user_username} de esta organización?`)) {
      return;
    }
    setError("");
    try {
      await api.remove(`/memberships/${member.id}/`);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Membresías"
      lede="Usuarios que operan esta organización y el rol con el que entran."
      actions={
        canEdit ? (
          <Button type="button" onClick={() => setCreating(true)}>
            Nuevo usuario
          </Button>
        ) : null
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      {memberships.isLoading ? <Loading /> : null}
      {(memberships.data?.results.length ?? 0) === 0 && !memberships.isLoading ? (
        <Empty>No hay membresías.</Empty>
      ) : null}
      {(memberships.data?.results.length ?? 0) > 0 ? (
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Membresías</caption>
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Correo</th>
                <th>Rol</th>
                {canEdit ? <th>Acciones</th> : null}
              </tr>
            </thead>
            <tbody>
              {memberships.data?.results.map((member) => (
                <tr key={member.id}>
                  <td>{member.user_username}</td>
                  <td>{member.user_email}</td>
                  <td>{ROLE_LABEL[member.role]}</td>
                  {canEdit ? (
                    <td className="row-actions">
                      <button
                        type="button"
                        onClick={() => {
                          setEditing(member);
                          roleForm.reset({ role: member.role });
                        }}
                      >
                        Cambiar rol
                      </button>
                      <button type="button" onClick={() => void remove(member)}>
                        Quitar
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
        <Modal title="Nuevo usuario" onClose={() => setCreating(false)}>
          <form className="form-grid" onSubmit={form.handleSubmit(createMember)}>
            <Field label="Usuario" error={form.formState.errors.username?.message}>
              <input {...form.register("username")} autoComplete="off" />
            </Field>
            <Field label="Correo" error={form.formState.errors.email?.message}>
              <input type="email" {...form.register("email")} />
            </Field>
            <Field label="Contraseña" error={form.formState.errors.password?.message}>
              <input type="password" {...form.register("password")} autoComplete="new-password" />
            </Field>
            <Field label="Nombre">
              <input {...form.register("first_name")} />
            </Field>
            <Field label="Apellido">
              <input {...form.register("last_name")} />
            </Field>
            <Field label="Rol">
              <select {...form.register("role")}>
                <option value="ADMIN">Administrador</option>
                <option value="OPERATOR">Operador</option>
                <option value="VIEWER">Consulta</option>
              </select>
            </Field>
            <Button type="submit" disabled={form.formState.isSubmitting}>
              Guardar membresía
            </Button>
          </form>
        </Modal>
      ) : null}
      {editing ? (
        <Modal title={`Rol de ${editing.user_username}`} onClose={() => setEditing(null)}>
          <form className="form-grid" onSubmit={roleForm.handleSubmit(saveRole)}>
            <Field label="Rol">
              <select {...roleForm.register("role")}>
                <option value="ADMIN">Administrador</option>
                <option value="OPERATOR">Operador</option>
                <option value="VIEWER">Consulta</option>
              </select>
            </Field>
            <Button type="submit">Guardar rol</Button>
          </form>
        </Modal>
      ) : null}
    </Page>
  );
}

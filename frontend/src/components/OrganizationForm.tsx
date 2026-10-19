import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Organization } from "@/api/types";
import { changeOrganization } from "@/auth/actions";
import { useSession } from "@/auth/session";
import { Banner, Button, Field, Loading } from "@/components/ui";
import { slugify } from "@/lib/access";
import { errorMessage } from "@/lib/errors";
import { zoneOptions } from "@/lib/time";

const schema = z.object({
  name: z.string().trim().min(1, "Indique el nombre."),
  slug: z
    .string()
    .trim()
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use minúsculas, números y guiones."),
  timezone: z.string().min(1, "Elija una zona horaria."),
  is_active: z.boolean(),
  admin_username: z.string(),
  admin_email: z.string(),
  admin_password: z.string(),
});

type FormValues = z.infer<typeof schema>;

export function OrganizationForm({
  organization,
  onSaved,
}: {
  organization?: Organization | null;
  onSaved: (organization: Organization) => void;
}) {
  const [slugTouched, setSlugTouched] = useState(Boolean(organization));
  const [error, setError] = useState("");
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: organization?.name ?? "",
      slug: organization?.slug ?? "",
      timezone: organization?.timezone ?? "America/Bogota",
      is_active: organization?.is_active ?? true,
      admin_username: "",
      admin_email: "",
      admin_password: "",
    },
  });

  useEffect(() => {
    form.reset({
      name: organization?.name ?? "",
      slug: organization?.slug ?? "",
      timezone: organization?.timezone ?? "America/Bogota",
      is_active: organization?.is_active ?? true,
      admin_username: "",
      admin_email: "",
      admin_password: "",
    });
    setSlugTouched(Boolean(organization));
  }, [organization, form]);

  async function onSubmit(values: FormValues) {
    setError("");
    const body: Record<string, unknown> = {
      name: values.name,
      slug: values.slug,
      timezone: values.timezone,
      is_active: values.is_active,
    };
    if (!organization && values.admin_username) {
      body.initial_admin = {
        username: values.admin_username,
        email: values.admin_email,
        password: values.admin_password,
      };
    }
    try {
      const saved = organization
        ? await api.update<Organization>(`/organizations/${organization.id}/`, body)
        : await api.create<Organization>("/organizations/", body);
      onSaved(saved);
      if (!organization) {
        form.reset();
        setSlugTouched(false);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <form className="form-grid" onSubmit={form.handleSubmit(onSubmit)}>
      {error ? <Banner>{error}</Banner> : null}
      <Field label="Nombre" error={form.formState.errors.name?.message}>
        <input
          {...form.register("name", {
            onChange: (event) => {
              if (!slugTouched) {
                form.setValue("slug", slugify(event.target.value));
              }
            },
          })}
        />
      </Field>
      <Field label="Identificador" error={form.formState.errors.slug?.message}>
        <input
          {...form.register("slug", {
            onChange: () => setSlugTouched(true),
          })}
        />
      </Field>
      <Field label="Zona horaria" error={form.formState.errors.timezone?.message}>
        <select {...form.register("timezone")}>
          {zoneOptions(organization?.timezone).map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
      </Field>
      <label className="check">
        <input type="checkbox" {...form.register("is_active")} />
        Activa
      </label>
      {organization ? null : (
        <fieldset className="subform">
          <legend>Administrador inicial (opcional)</legend>
          <Field label="Usuario">
            <input {...form.register("admin_username")} autoComplete="off" />
          </Field>
          <Field label="Correo del administrador">
            <input type="email" {...form.register("admin_email")} />
          </Field>
          <Field label="Contraseña inicial">
            <input
              type="password"
              {...form.register("admin_password")}
              autoComplete="new-password"
            />
          </Field>
        </fieldset>
      )}
      <div className="form-actions">
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {organization ? "Guardar organización" : "Crear organización"}
        </Button>
      </div>
    </form>
  );
}

export function OrgPicker() {
  const user = useSession((state) => state.user);
  const isSuperadmin = useSession((state) => state.isSuperadmin);
  const clear = useSession((state) => state.clear);
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const organizations = useOrgQuery(
    ["/organizations/", "picker"],
    () => api.list<Organization>("/organizations/", { page_size: 100, is_active: true }),
    { enabled: isSuperadmin, scoped: false },
  );

  const memberships = user?.memberships ?? [];
  const platform = organizations.data?.results ?? [];

  async function enter(organizationId: string) {
    setError("");
    try {
      await changeOrganization(organizationId, queryClient);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <main className="gate">
      <section className="gate-card">
        <p className="eyebrow">Organización activa</p>
        <h1>Elija dónde va a trabajar</h1>
        <p>
          {user?.username}, los datos del panel pertenecen a una organización a la vez. Puede
          cambiar después desde la barra superior.
        </p>
        {error ? <Banner>{error}</Banner> : null}
        {isSuperadmin && organizations.isLoading ? <Loading /> : null}
        <ul className="choice-list">
          {(isSuperadmin ? platform : memberships).map((item) => {
            const id = "id" in item ? item.id : item.organization_id;
            const name = item.name;
            return (
              <li key={id}>
                <span>{name}</span>
                <Button type="button" onClick={() => void enter(id)}>
                  Entrar
                </Button>
              </li>
            );
          })}
        </ul>
        {isSuperadmin ? (
          <div className="stack">
            <Button type="button" variant="ghost" onClick={() => setCreating((value) => !value)}>
              Nueva organización
            </Button>
            {creating ? (
              <OrganizationForm
                onSaved={(organization) => {
                  void enter(organization.id);
                }}
              />
            ) : null}
          </div>
        ) : null}
        <button type="button" className="text-btn" onClick={clear}>
          Cerrar sesión
        </button>
      </section>
    </main>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Credential, Department, Employee, ReaderProfile } from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Modal, Page, Pager } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { CREDENTIAL_SOURCE_LABEL, CREDENTIAL_TYPE_LABEL, personName } from "@/lib/labels";
import { formatStamp, fromDateTimeLocal } from "@/lib/time";

const employeeSchema = z.object({
  document_id: z.string().trim().min(1, "Indique el documento."),
  first_name: z.string().trim().min(1, "Indique el nombre."),
  last_name: z.string().trim().min(1, "Indique el apellido."),
  email: z
    .string()
    .trim()
    .refine(
      (value) => value === "" || z.string().email().safeParse(value).success,
      "Correo inválido.",
    ),
  department: z.string(),
  is_active: z.boolean(),
});

const credentialSchema = z
  .object({
    type: z.enum(["RFID", "FINGERPRINT", "PIN", "FACIAL"]),
    payload: z.string().trim().min(1, "Indique el identificador."),
    source: z.enum(["MANUAL", "ASSISTED_ENROLLMENT", "FACEAUTH"]),
    reader_profile: z.string(),
    valid_from: z.string(),
    valid_until: z.string(),
    is_active: z.boolean(),
  })
  .superRefine((value, context) => {
    if (value.type === "FACIAL" && !z.string().uuid().safeParse(value.payload).success) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["payload"],
        message: "Para rostro, el identificador es el UUID de Face-Auth.",
      });
    }
    if (value.valid_from && value.valid_until && value.valid_until < value.valid_from) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["valid_until"],
        message: "La vigencia final es anterior al inicio.",
      });
    }
  });

type EmployeeForm = z.infer<typeof employeeSchema>;
type CredentialForm = z.infer<typeof credentialSchema>;

const emptyEmployee: EmployeeForm = {
  document_id: "",
  first_name: "",
  last_name: "",
  email: "",
  department: "",
  is_active: true,
};

const emptyCredential: CredentialForm = {
  type: "RFID",
  payload: "",
  source: "MANUAL",
  reader_profile: "",
  valid_from: "",
  valid_until: "",
  is_active: true,
};

function employeeValues(employee: Employee): EmployeeForm {
  return {
    document_id: employee.document_id,
    first_name: employee.first_name,
    last_name: employee.last_name,
    email: employee.email ?? "",
    department: employee.department ?? "",
    is_active: employee.is_active,
  };
}

export function EmployeesPage({ canEdit }: { canEdit: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const timeZone = usePreferences((state) => state.timeZone);
  const search = usePreferences((state) => state.employeeSearch);
  const setSearch = usePreferences((state) => state.setEmployeeSearch);
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Employee | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const employees = useOrgQuery(["/employees/", page, search], () =>
    api.list<Employee>("/employees/", {
      page,
      page_size: 20,
      search,
      ordering: "last_name",
    }),
  );
  const departments = useOrgQuery(["/departments/", "lookup"], () =>
    api.list<Department>("/departments/", { page_size: 100, ordering: "name", is_active: true }),
  );
  const profiles = useOrgQuery(["/reader-profiles/", "lookup"], () =>
    api.list<ReaderProfile>("/reader-profiles/", { page_size: 100, is_active: true }),
  );
  const credentials = useOrgQuery(
    ["/credentials/", selected?.id ?? ""],
    () => api.list<Credential>("/credentials/", { employee: selected?.id, page_size: 100 }),
    { enabled: Boolean(selected) },
  );

  const employeeForm = useForm<EmployeeForm>({
    resolver: zodResolver(employeeSchema),
    defaultValues: emptyEmployee,
  });
  const editForm = useForm<EmployeeForm>({
    resolver: zodResolver(employeeSchema),
    defaultValues: emptyEmployee,
  });
  const credentialForm = useForm<CredentialForm>({
    resolver: zodResolver(credentialSchema),
    defaultValues: emptyCredential,
  });

  useEffect(() => {
    if (selected) {
      editForm.reset(employeeValues(selected));
    }
  }, [selected, editForm]);

  async function refreshEmployees() {
    await queryClient.invalidateQueries({ queryKey: [organizationId, "/employees/"] });
  }

  async function createEmployee(values: EmployeeForm) {
    setError("");
    try {
      const created = await api.create<Employee>("/employees/", {
        ...values,
        email: values.email || null,
        department: values.department || null,
      });
      setCreating(false);
      employeeForm.reset(emptyEmployee);
      setSelected(created);
      setNotice("Empleado registrado.");
      await refreshEmployees();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function saveEmployee(values: EmployeeForm) {
    if (!selected) {
      return;
    }
    setError("");
    try {
      const updated = await api.update<Employee>(`/employees/${selected.id}/`, {
        ...values,
        email: values.email || null,
        department: values.department || null,
      });
      setSelected(updated);
      setNotice("Empleado actualizado.");
      await refreshEmployees();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function saveCredential(values: CredentialForm) {
    if (!selected) {
      return;
    }
    setError("");
    try {
      await api.create<Credential>("/credentials/", {
        employee: selected.id,
        type: values.type,
        payload: values.payload,
        source: values.source,
        reader_profile: values.reader_profile || null,
        valid_from: fromDateTimeLocal(values.valid_from, timeZone),
        valid_until: fromDateTimeLocal(values.valid_until, timeZone),
        is_active: values.is_active,
      });
      credentialForm.reset(emptyCredential);
      setNotice("Credencial registrada.");
      await queryClient.invalidateQueries({
        queryKey: [organizationId, "/credentials/", selected.id],
      });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function toggleCredential(credential: Credential) {
    setError("");
    try {
      if (credential.is_active) {
        await api.remove(`/credentials/${credential.id}/`);
      } else {
        await api.update(`/credentials/${credential.id}/`, { is_active: true });
      }
      await queryClient.invalidateQueries({
        queryKey: [organizationId, "/credentials/", selected?.id],
      });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const departmentName = new Map(
    (departments.data?.results ?? []).map((item) => [item.id, item.name]),
  );
  const profileName = new Map((profiles.data?.results ?? []).map((item) => [item.id, item.name]));

  return (
    <Page
      title="Empleados"
      lede="Alta de personas y de sus credenciales. El agente las recibe en el siguiente delta."
      actions={
        canEdit ? (
          <Button type="button" onClick={() => setCreating(true)}>
            Nuevo empleado
          </Button>
        ) : null
      }
    >
      {notice ? <Banner tone="ok">{notice}</Banner> : null}
      {error ? <Banner>{error}</Banner> : null}
      <div className="toolbar">
        <Field label="Buscar">
          <input
            value={search}
            onChange={(event) => {
              setPage(1);
              setSearch(event.target.value);
            }}
            placeholder="Documento, nombre o correo"
          />
        </Field>
      </div>
      {employees.isLoading ? <Loading /> : null}
      {employees.isError ? <Banner>{errorMessage(employees.error)}</Banner> : null}
      <div className="split">
        <div>
          {(employees.data?.results.length ?? 0) === 0 && !employees.isLoading ? (
            <Empty>No hay empleados con ese criterio.</Empty>
          ) : null}
          {(employees.data?.results.length ?? 0) > 0 ? (
            <div className="table-wrap">
              <table className="grid">
                <caption className="sr-only">Empleados</caption>
                <thead>
                  <tr>
                    <th>Documento</th>
                    <th>Nombre</th>
                    <th>Departamento</th>
                    <th>Presencia</th>
                  </tr>
                </thead>
                <tbody>
                  {employees.data?.results.map((employee) => (
                    <tr
                      key={employee.id}
                      className={selected?.id === employee.id ? "selected" : ""}
                    >
                      <td>{employee.document_id}</td>
                      <td>
                        <button
                          type="button"
                          className="linkish"
                          onClick={() => setSelected(employee)}
                        >
                          {personName(employee)}
                        </button>
                      </td>
                      <td>
                        {employee.department
                          ? (departmentName.get(employee.department) ?? "—")
                          : "—"}
                      </td>
                      <td>{employee.is_inside ? "Dentro" : "Fuera"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <Pager page={page} count={employees.data?.count ?? 0} pageSize={20} onPage={setPage} />
        </div>
        {selected ? (
          <aside className="detail card">
            <h2>{personName(selected)}</h2>
            <p className="muted">
              {selected.is_active ? "Activo" : "Inactivo"}
              {selected.email ? ` · ${selected.email}` : " · sin correo"}
            </p>
            {canEdit ? (
              <form className="form-grid" onSubmit={editForm.handleSubmit(saveEmployee)}>
                <EmployeeFields
                  register={editForm.register}
                  errors={editForm.formState.errors}
                  departments={departments.data?.results ?? []}
                />
                <Button type="submit" disabled={editForm.formState.isSubmitting}>
                  Guardar empleado
                </Button>
              </form>
            ) : null}
            <h3>Credenciales</h3>
            {credentials.isLoading ? <Loading /> : null}
            {credentials.isError ? <Banner>{errorMessage(credentials.error)}</Banner> : null}
            {(credentials.data?.results.length ?? 0) === 0 &&
            !credentials.isLoading &&
            !credentials.isError ? (
              <Empty>Este empleado todavía no tiene credenciales.</Empty>
            ) : null}
            <ul className="credential-list">
              {credentials.data?.results.map((credential) => (
                <li key={credential.id}>
                  <div>
                    <strong>{CREDENTIAL_TYPE_LABEL[credential.type] ?? credential.type}</strong>
                    <code>{credential.payload}</code>
                    <small>
                      {CREDENTIAL_SOURCE_LABEL[credential.source] ?? credential.source}
                      {credential.reader_profile
                        ? ` · ${profileName.get(credential.reader_profile) ?? "perfil"}`
                        : ""}
                      {credential.valid_from
                        ? ` · desde ${formatStamp(credential.valid_from, timeZone)}`
                        : ""}
                      {credential.valid_until
                        ? ` · hasta ${formatStamp(credential.valid_until, timeZone)}`
                        : ""}
                      {credential.is_active ? "" : " · inactiva"}
                    </small>
                  </div>
                  {canEdit ? (
                    <button type="button" onClick={() => void toggleCredential(credential)}>
                      {credential.is_active ? "Desactivar" : "Reactivar"}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
            {canEdit ? (
              <form className="form-grid" onSubmit={credentialForm.handleSubmit(saveCredential)}>
                <h3>Nueva credencial</h3>
                <CredentialFields
                  register={credentialForm.register}
                  errors={credentialForm.formState.errors}
                  profiles={profiles.data?.results ?? []}
                  type={credentialForm.watch("type")}
                />
                <Button type="submit" disabled={credentialForm.formState.isSubmitting}>
                  Guardar credencial
                </Button>
              </form>
            ) : null}
          </aside>
        ) : (
          <aside className="detail card">
            <Empty>Seleccione un empleado para ver sus credenciales.</Empty>
          </aside>
        )}
      </div>
      {creating ? (
        <Modal title="Nuevo empleado" onClose={() => setCreating(false)}>
          <form className="form-grid" onSubmit={employeeForm.handleSubmit(createEmployee)}>
            <EmployeeFields
              register={employeeForm.register}
              errors={employeeForm.formState.errors}
              departments={departments.data?.results ?? []}
            />
            <div className="form-actions">
              <Button type="submit" disabled={employeeForm.formState.isSubmitting}>
                Guardar empleado
              </Button>
            </div>
          </form>
        </Modal>
      ) : null}
    </Page>
  );
}

function EmployeeFields({
  register,
  errors,
  departments,
}: {
  register: ReturnType<typeof useForm<EmployeeForm>>["register"];
  errors: ReturnType<typeof useForm<EmployeeForm>>["formState"]["errors"];
  departments: Department[];
}) {
  return (
    <>
      <Field label="Documento" error={errors.document_id?.message}>
        <input {...register("document_id")} />
      </Field>
      <Field label="Nombre" error={errors.first_name?.message}>
        <input {...register("first_name")} />
      </Field>
      <Field label="Apellido" error={errors.last_name?.message}>
        <input {...register("last_name")} />
      </Field>
      <Field label="Correo" error={errors.email?.message}>
        <input type="email" {...register("email")} />
      </Field>
      <Field label="Departamento">
        <select {...register("department")}>
          <option value="">Sin departamento</option>
          {departments.map((department) => (
            <option key={department.id} value={department.id}>
              {department.name}
            </option>
          ))}
        </select>
      </Field>
      <label className="check">
        <input type="checkbox" {...register("is_active")} />
        Activo
      </label>
    </>
  );
}

function CredentialFields({
  register,
  errors,
  profiles,
  type,
}: {
  register: ReturnType<typeof useForm<CredentialForm>>["register"];
  errors: ReturnType<typeof useForm<CredentialForm>>["formState"]["errors"];
  profiles: ReaderProfile[];
  type: CredentialForm["type"];
}) {
  const matching = profiles.filter((profile) => profile.credential_type === type);
  return (
    <>
      <Field label="Tipo" error={errors.type?.message}>
        <select {...register("type")}>
          {Object.entries(CREDENTIAL_TYPE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Identificador" error={errors.payload?.message}>
        <input {...register("payload")} />
      </Field>
      {type === "FACIAL" ? (
        <p className="hint">El identificador facial es el user_id de Face-Auth, no una imagen.</p>
      ) : null}
      <Field label="Origen">
        <select {...register("source")}>
          {Object.entries(CREDENTIAL_SOURCE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Perfil de lector">
        <select {...register("reader_profile")}>
          <option value="">Sin perfil</option>
          {matching.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Vigente desde">
        <input type="datetime-local" {...register("valid_from")} />
      </Field>
      <Field label="Vigente hasta" error={errors.valid_until?.message}>
        <input type="datetime-local" {...register("valid_until")} />
      </Field>
      <label className="check">
        <input type="checkbox" {...register("is_active")} />
        Activa
      </label>
    </>
  );
}

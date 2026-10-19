import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { api } from "@/api/client";
import type { Me } from "@/api/types";
import { renderRoutes, signIn } from "@/test/render";

const operator: Me = {
  id: "user-1",
  username: "acme.operator",
  email: "operator@acme.test",
  first_name: "Ada",
  last_name: "Admin",
  is_superadmin: false,
  organization_id: "org-1",
  role: "OPERATOR",
  memberships: [{ organization_id: "org-1", name: "Acme", slug: "acme", role: "OPERATOR" }],
};

test("pide credenciales cuando no hay sesión", async () => {
  renderRoutes("/empleados");
  expect(
    await screen.findByRole("heading", { name: /control y registro de acceso/i }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Usuario")).toBeInTheDocument();
});

test("muestra el panel tras un ingreso válido", async () => {
  vi.mocked(api.login).mockResolvedValue({
    access: "access-token",
    refresh: "refresh-token",
    organization_id: "org-1",
    role: "OPERATOR",
    is_superadmin: false,
  });
  vi.mocked(api.me).mockResolvedValue(operator);
  renderRoutes("/login");
  fireEvent.change(screen.getByLabelText("Usuario"), { target: { value: "acme.operator" } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "secreta" } });
  fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
  expect(await screen.findByRole("heading", { name: "Nodos" })).toBeInTheDocument();
});

test("informa cuando las credenciales no sirven", async () => {
  vi.mocked(api.login).mockRejectedValue({ response: { status: 401 } });
  renderRoutes("/login");
  fireEvent.change(screen.getByLabelText("Usuario"), { target: { value: "acme.operator" } });
  fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "mala" } });
  fireEvent.click(screen.getByRole("button", { name: "Entrar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Usuario o contraseña incorrectos.");
});

test("un perfil de consulta no puede dar de alta empleados", async () => {
  signIn("VIEWER");
  renderRoutes("/empleados");
  expect(await screen.findByRole("heading", { name: "Empleados" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Nuevo empleado" })).not.toBeInTheDocument();
});

test("un operador registra un empleado y su credencial", async () => {
  signIn("OPERATOR");
  vi.mocked(api.create).mockImplementation((path: string, body?: unknown) => {
    const payload = (body ?? {}) as Record<string, unknown>;
    if (path === "/employees/") {
      return Promise.resolve({
        id: "emp-1",
        organization: "org-1",
        department: null,
        document_id: payload.document_id,
        first_name: payload.first_name,
        last_name: payload.last_name,
        email: payload.email,
        is_active: true,
        is_inside: false,
        last_presence_at: null,
        deleted_at: null,
        version: 1,
        created_at: "2026-10-18T12:00:00Z",
        updated_at: "2026-10-18T12:00:00Z",
      });
    }
    return Promise.resolve({
      id: "cred-1",
      organization: "org-1",
      employee: "emp-1",
      reader_profile: null,
      valid_from: null,
      valid_until: null,
      deleted_at: null,
      version: 2,
      created_at: "2026-10-18T12:00:00Z",
      updated_at: "2026-10-18T12:00:00Z",
      ...payload,
    });
  });

  renderRoutes("/empleados");
  fireEvent.click(await screen.findByRole("button", { name: "Nuevo empleado" }));
  const dialog = await screen.findByRole("dialog", { name: "Nuevo empleado" });
  const form = within(dialog);
  fireEvent.change(form.getByLabelText("Documento"), { target: { value: "9001" } });
  fireEvent.change(form.getByLabelText("Nombre"), { target: { value: "Lucía" } });
  fireEvent.change(form.getByLabelText("Apellido"), { target: { value: "Pardo" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar empleado" }));

  expect(await screen.findByText("Empleado registrado.")).toBeInTheDocument();
  await waitFor(() => {
    expect(api.create).toHaveBeenCalledWith(
      "/employees/",
      expect.objectContaining({ document_id: "9001", first_name: "Lucía", last_name: "Pardo" }),
    );
  });

  fireEvent.change(screen.getByLabelText("Identificador"), { target: { value: "00AB12" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar credencial" }));
  expect(await screen.findByText("Credencial registrada.")).toBeInTheDocument();
  await waitFor(() => {
    expect(api.create).toHaveBeenCalledWith(
      "/credentials/",
      expect.objectContaining({
        employee: "emp-1",
        type: "RFID",
        payload: "00AB12",
        source: "MANUAL",
      }),
    );
  });
});

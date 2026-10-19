import { expect, test } from "@playwright/test";

test("un operador registra un empleado y una credencial", async ({ page }) => {
  const employees: Record<string, unknown>[] = [];
  const credentials: Record<string, unknown>[] = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && path.endsWith("/auth/token/")) {
      await route.fulfill({
        json: {
          access: "access-token",
          refresh: "refresh-token",
          organization_id: "org-1",
          role: "OPERATOR",
          is_superadmin: false,
        },
      });
      return;
    }
    if (path.endsWith("/auth/me/")) {
      await route.fulfill({
        json: {
          id: "user-1",
          username: "acme.operator",
          email: "operator@acme.test",
          first_name: "Ada",
          last_name: "Admin",
          is_superadmin: false,
          organization_id: "org-1",
          role: "OPERATOR",
          memberships: [{ organization_id: "org-1", name: "Acme", slug: "acme", role: "OPERATOR" }],
        },
      });
      return;
    }
    if (request.method() === "POST" && path.endsWith("/employees/")) {
      const body = request.postDataJSON() as Record<string, unknown>;
      const employee = {
        id: "emp-1",
        organization: "org-1",
        department: null,
        is_inside: false,
        last_presence_at: null,
        deleted_at: null,
        version: 1,
        created_at: "2026-10-18T12:00:00Z",
        updated_at: "2026-10-18T12:00:00Z",
        ...body,
      };
      employees.push(employee);
      await route.fulfill({ json: employee });
      return;
    }
    if (request.method() === "GET" && path.endsWith("/employees/")) {
      await route.fulfill({
        json: { count: employees.length, next: null, previous: null, results: employees },
      });
      return;
    }
    if (request.method() === "POST" && path.endsWith("/credentials/")) {
      const body = request.postDataJSON() as Record<string, unknown>;
      const credential = { id: "cred-1", organization: "org-1", ...body };
      credentials.push(credential);
      await route.fulfill({ json: credential });
      return;
    }
    if (request.method() === "GET" && path.endsWith("/credentials/")) {
      await route.fulfill({
        json: { count: credentials.length, next: null, previous: null, results: credentials },
      });
      return;
    }
    await route.fulfill({
      json: { count: 0, next: null, previous: null, results: [] },
    });
  });

  await page.goto("/login");
  await page.getByLabel("Usuario").fill("acme.operator");
  await page.getByLabel("Contraseña").fill("Nube-Segura-2026!");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("link", { name: "Empleados" }).click();
  await page.getByRole("button", { name: "Nuevo empleado" }).click();
  const dialog = page.getByRole("dialog", { name: "Nuevo empleado" });
  await dialog.getByLabel("Documento").fill("9001");
  await dialog.getByLabel("Nombre").fill("Lucía");
  await dialog.getByLabel("Apellido").fill("Pardo");
  await dialog.getByRole("button", { name: "Guardar empleado" }).click();
  await expect(page.getByText("Empleado registrado.")).toBeVisible();
  await page.getByLabel("Identificador").fill("00AB12");
  await page.getByRole("button", { name: "Guardar credencial" }).click();
  await expect(page.getByText("Credencial registrada.")).toBeVisible();
  await expect(page.getByText("00AB12")).toBeVisible();
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes } from "@/App";
import type { Me, Role } from "@/api/types";
import { useSession } from "@/auth/session";

export function renderRoutes(path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<AppRoutes />, {
    wrapper: ({ children }) => (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
      </QueryClientProvider>
    ),
  });
}

export function signIn(role: Role = "OPERATOR", extra: Partial<Me> = {}) {
  const user: Me = {
    id: "user-1",
    username: "acme.operator",
    email: "operator@acme.test",
    first_name: "Ada",
    last_name: "Admin",
    is_superadmin: role === "SUPERADMIN",
    organization_id: "org-1",
    role,
    memberships: [
      {
        organization_id: "org-1",
        name: "Acme",
        slug: "acme",
        role: role === "SUPERADMIN" ? "ADMIN" : role,
      },
    ],
    ...extra,
  };
  useSession.setState({
    access: "access-token",
    refresh: "refresh-token",
    organizationId: user.organization_id,
    role: user.role,
    isSuperadmin: user.is_superadmin,
    user,
    hydrated: true,
  });
}

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Organization, Role } from "@/api/types";
import { changeOrganization } from "@/auth/actions";
import { useSession } from "@/auth/session";
import { canOperate } from "@/lib/access";
import { errorMessage } from "@/lib/errors";
import { ROLE_LABEL } from "@/lib/labels";

import { Banner } from "./ui";

const NAV: { to: string; label: string; allow?: "ops" | "platform" }[] = [
  { to: "/", label: "Tablero" },
  { to: "/nodos", label: "Nodos" },
  { to: "/empleados", label: "Empleados" },
  { to: "/departamentos", label: "Departamentos" },
  { to: "/zonas", label: "Zonas" },
  { to: "/puertas", label: "Puertas" },
  { to: "/perfiles", label: "Perfiles de lector" },
  { to: "/marcaciones", label: "Marcaciones" },
  { to: "/anomalias", label: "Anomalías" },
  { to: "/enrolamiento", label: "Enrolamiento", allow: "ops" },
  { to: "/kioscos", label: "Kioscos" },
  { to: "/rostro", label: "Rostro" },
  { to: "/membresias", label: "Membresías" },
  { to: "/organizaciones", label: "Organizaciones", allow: "platform" },
];

function visible(item: (typeof NAV)[number], role: Role | null, isSuperadmin: boolean) {
  if (item.allow === "platform") {
    return isSuperadmin;
  }
  if (item.allow === "ops") {
    return canOperate(role);
  }
  return true;
}

export function Layout() {
  const user = useSession((state) => state.user);
  const role = useSession((state) => state.role);
  const organizationId = useSession((state) => state.organizationId);
  const isSuperadmin = useSession((state) => state.isSuperadmin);
  const clear = useSession((state) => state.clear);
  const queryClient = useQueryClient();
  const [orgError, setOrgError] = useState("");
  const organizations = useOrgQuery(
    ["/organizations/", "switcher"],
    () => api.list<Organization>("/organizations/", { page_size: 100 }),
    { enabled: isSuperadmin },
  );

  const membershipChoices = (user?.memberships ?? []).map((item) => ({
    id: item.organization_id,
    label: item.name,
  }));
  const platformChoices = (organizations.data?.results ?? []).map((item) => ({
    id: item.id,
    label: item.name,
  }));
  const choices = isSuperadmin && platformChoices.length > 0 ? platformChoices : membershipChoices;
  const showSwitcher = isSuperadmin || choices.length > 1;

  async function onOrganization(nextId: string) {
    if (!nextId || nextId === organizationId) {
      return;
    }
    setOrgError("");
    try {
      await changeOrganization(nextId, queryClient);
    } catch (error) {
      setOrgError(errorMessage(error));
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <p className="brand">
          <span>Control de acceso</span>
          Panel
        </p>
        <nav aria-label="Secciones">
          {NAV.filter((item) => visible(item, role, isSuperadmin)).map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="org-switch">
            {showSwitcher ? (
              <label>
                Organización
                <select
                  aria-label="Organización"
                  value={organizationId ?? ""}
                  onChange={(event) => {
                    void onOrganization(event.target.value);
                  }}
                >
                  {choices.map((choice) => (
                    <option key={choice.id} value={choice.id}>
                      {choice.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <strong>{choices[0]?.label ?? "Organización"}</strong>
            )}
          </div>
          <div className="who">
            <span>
              {user?.username}
              {role ? ` · ${ROLE_LABEL[role]}` : ""}
            </span>
            <NavLink to="/preferencias">Preferencias</NavLink>
            <button type="button" onClick={clear}>
              Cerrar sesión
            </button>
          </div>
        </header>
        {orgError ? <Banner>{orgError}</Banner> : null}
        <main>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Organization } from "@/api/types";
import { OrganizationForm } from "@/components/OrganizationForm";
import { Banner, Button, Empty, Loading, Page } from "@/components/ui";
import { errorMessage } from "@/lib/errors";

export function OrganizationsPage() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Organization | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const organizations = useOrgQuery(
    ["/organizations/"],
    () => api.list<Organization>("/organizations/", { page_size: 100, ordering: "name" }),
    { scoped: false },
  );

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["platform", "/organizations/"] });
  }

  async function deactivate(organization: Organization) {
    if (!window.confirm(`Desactivar «${organization.name}»?`)) {
      return;
    }
    setError("");
    try {
      await api.remove(`/organizations/${organization.id}/`);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Organizaciones"
      lede="Alta de clientes de la plataforma. Cada una aísla sus empleados, nodos y marcaciones."
      actions={
        <Button
          type="button"
          onClick={() => {
            setSelected(null);
            setCreating(true);
          }}
        >
          Nueva organización
        </Button>
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      {organizations.isLoading ? <Loading /> : null}
      <div className="split">
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Organizaciones</caption>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Identificador</th>
                <th>Zona</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {organizations.data?.results.map((organization) => (
                <tr key={organization.id}>
                  <td>
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => {
                        setCreating(false);
                        setSelected(organization);
                      }}
                    >
                      {organization.name}
                    </button>
                  </td>
                  <td>{organization.slug}</td>
                  <td>{organization.timezone}</td>
                  <td>{organization.is_active ? "Activa" : "Inactiva"}</td>
                  <td>
                    {organization.is_active ? (
                      <button type="button" onClick={() => void deactivate(organization)}>
                        Desactivar
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(organizations.data?.results.length ?? 0) === 0 && !organizations.isLoading ? (
            <Empty>No hay organizaciones.</Empty>
          ) : null}
        </div>
        {creating || selected ? (
          <aside className="detail card">
            <h2>{selected ? selected.name : "Nueva organización"}</h2>
            <OrganizationForm
              organization={creating ? null : selected}
              onSaved={() => {
                setCreating(false);
                setSelected(null);
                void refresh();
              }}
            />
          </aside>
        ) : null}
      </div>
    </Page>
  );
}

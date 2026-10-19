import { useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { api } from "@/api/client";
import { usePreferences } from "@/auth/preferences";
import { useSession } from "@/auth/session";
import { Layout } from "@/components/Layout";
import { OrgPicker } from "@/components/OrganizationForm";
import { canAdminister, canOperate } from "@/lib/access";
import { AnomaliesPage } from "@/pages/AnomaliesPage";
import { CatalogPage } from "@/pages/CatalogPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DoorsPage } from "@/pages/DoorsPage";
import { EmployeesPage } from "@/pages/EmployeesPage";
import { FaceEnrollPage } from "@/pages/FaceEnrollPage";
import { FacePage } from "@/pages/FacePage";
import { FaceEnrollReturn, FaceLoginReturn } from "@/pages/FaceReturnPage";
import { EnrollmentPage } from "@/pages/EnrollmentPage";
import { KioskPage } from "@/pages/KioskPage";
import { KiosksPage } from "@/pages/KiosksPage";
import { LoginPage } from "@/pages/LoginPage";
import { LogsPage } from "@/pages/LogsPage";
import { MembershipsPage } from "@/pages/MembershipsPage";
import { NodesPage } from "@/pages/NodesPage";
import { OrganizationsPage } from "@/pages/OrganizationsPage";
import { PreferencesPage } from "@/pages/PreferencesPage";
import { ProfilesPage } from "@/pages/ProfilesPage";

function ThemeSync() {
  const theme = usePreferences((state) => state.theme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return null;
}

function HydrateStores() {
  useEffect(() => {
    if (import.meta.env.MODE === "test") {
      useSession.setState({ hydrated: true });
      return;
    }
    void useSession.persist.rehydrate();
    void usePreferences.persist.rehydrate();
  }, []);
  return null;
}

function SessionGate({ children }: { children: ReactNode }) {
  const hydrated = useSession((state) => state.hydrated);
  const access = useSession((state) => state.access);

  useEffect(() => {
    if (import.meta.env.MODE === "test" || !hydrated || !access) {
      return;
    }
    let cancelled = false;
    api
      .me()
      .then((user) => {
        if (!cancelled) {
          useSession.getState().setUser(user);
        }
      })
      .catch(() => {
        if (!cancelled) {
          useSession.getState().clear();
        }
      });
    return () => {
      cancelled = true;
    };
  }, [hydrated, access]);

  if (!hydrated) {
    return <p className="boot">Cargando…</p>;
  }
  if (!access) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function Workspace() {
  const organizationId = useSession((state) => state.organizationId);
  if (!organizationId) {
    return <OrgPicker />;
  }
  return <Layout />;
}

function OperateOnly({ children }: { children: ReactNode }) {
  const role = useSession((state) => state.role);
  if (!canOperate(role)) {
    return <Navigate to="/nodos" replace />;
  }
  return children;
}

function PlatformOnly({ children }: { children: ReactNode }) {
  const isSuperadmin = useSession((state) => state.isSuperadmin);
  if (!isSuperadmin) {
    return <Navigate to="/nodos" replace />;
  }
  return children;
}

export function AppRoutes() {
  const role = useSession((state) => state.role);
  const operate = canOperate(role);
  const administer = canAdminister(role);

  return (
    <>
      <HydrateStores />
      <ThemeSync />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/kiosk/*" element={<KioskPage />} />
        <Route path="/auth/faceauth/return" element={<FaceLoginReturn />} />
        <Route path="/enroll/faceauth/callback" element={<FaceEnrollReturn />} />
        <Route
          element={
            <SessionGate>
              <Workspace />
            </SessionGate>
          }
        >
          <Route index element={<DashboardPage canReset={operate} />} />
          <Route path="nodos" element={<NodesPage canEdit={administer} />} />
          <Route path="empleados" element={<EmployeesPage canEdit={operate} />} />
          <Route
            path="departamentos"
            element={
              <CatalogPage
                title="Departamentos"
                lede="Agrupan empleados para los reportes posteriores."
                path="/departments/"
                canEdit={operate}
              />
            }
          />
          <Route
            path="zonas"
            element={
              <CatalogPage
                title="Zonas"
                lede="Las puertas pueden sumar aforo por zona."
                path="/zones/"
                canEdit={operate}
              />
            }
          />
          <Route path="puertas" element={<DoorsPage canEdit={operate} canOpen={operate} />} />
          <Route path="perfiles" element={<ProfilesPage canEdit={operate} />} />
          <Route path="marcaciones" element={<LogsPage />} />
          <Route path="anomalias" element={<AnomaliesPage />} />
          <Route
            path="enrolamiento"
            element={
              <OperateOnly>
                <EnrollmentPage />
              </OperateOnly>
            }
          />
          <Route path="kioscos" element={<KiosksPage canEdit={administer} />} />
          <Route path="rostro" element={<FacePage />} />
          <Route path="enrolar/:sessionId" element={<FaceEnrollPage />} />
          <Route path="membresias" element={<MembershipsPage canEdit={administer} />} />
          <Route path="preferencias" element={<PreferencesPage />} />
          <Route
            path="organizaciones"
            element={
              <PlatformOnly>
                <OrganizationsPage />
              </PlatformOnly>
            }
          />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

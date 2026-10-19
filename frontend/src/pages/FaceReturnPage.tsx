import axios from "axios";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, apiBaseUrl } from "@/api/client";
import type { TokenPair } from "@/api/types";
import { useSession } from "@/auth/session";
import { ENROLL_KEY } from "@/face/FaceEnrollWizard";
import { errorMessage } from "@/lib/errors";

const TOKEN_KEY = "attendance.kiosk.token";

function takeQueryToken(): string {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") ?? "";
  window.history.replaceState({}, "", window.location.pathname);
  return token;
}

export function FaceLoginReturn() {
  const navigate = useNavigate();
  const applyTokens = useSession((state) => state.applyTokens);
  const setUser = useSession((state) => state.setUser);
  const [error, setError] = useState("");

  useEffect(() => {
    const redirectToken = takeQueryToken();
    const orgSlug = sessionStorage.getItem("face.org") ?? "";
    sessionStorage.removeItem("face.org");
    if (!redirectToken || !orgSlug) {
      setError("El ingreso con rostro no trajo un token utilizable.");
      return;
    }
    axios
      .post<TokenPair>(`${apiBaseUrl}/auth/faceauth/callback/`, {
        redirect_token: redirectToken,
        org_slug: orgSlug,
      })
      .then(async (response) => {
        applyTokens(response.data);
        setUser(await api.me());
        navigate("/", { replace: true });
      })
      .catch((caught) => setError(errorMessage(caught)));
  }, [applyTokens, navigate, setUser]);

  return (
    <main className="gate">
      <section className="gate-card">
        <h1>Ingreso con rostro</h1>
        {error ? <p className="face-error">{error}</p> : <p>Confirmando la identidad…</p>}
      </section>
    </main>
  );
}

export function FaceEnrollReturn() {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    const redirectToken = takeQueryToken();
    const raw = sessionStorage.getItem(ENROLL_KEY);
    sessionStorage.removeItem(ENROLL_KEY);
    if (!redirectToken || !raw) {
      setError("No hay una sesión de enrolamiento abierta.");
      return;
    }
    const stored = JSON.parse(raw) as { sessionId: string; mode: "panel" | "kiosk" };
    const kioskToken = localStorage.getItem(TOKEN_KEY);
    const request =
      stored.mode === "kiosk" && kioskToken
        ? axios.post(
            `${apiBaseUrl}/face-enrollment-sessions/${stored.sessionId}/complete/`,
            { redirect_token: redirectToken },
            { headers: { Authorization: `Bearer ${kioskToken}` } },
          )
        : api.create(`/face-enrollment-sessions/${stored.sessionId}/complete/`, {
            redirect_token: redirectToken,
          });
    request.then(() => setDone(true)).catch((caught) => setError(errorMessage(caught)));
  }, []);

  return (
    <main className="gate">
      <section className="gate-card">
        <h1>Registro de rostro</h1>
        {error ? <p className="face-error">{error}</p> : null}
        {done ? <p>El rostro quedó registrado.</p> : null}
        {!error && !done ? <p>Confirmando el registro…</p> : null}
        <button
          type="button"
          className="linkish"
          onClick={() => navigate(done ? "/empleados" : "/kiosk")}
        >
          Volver
        </button>
      </section>
    </main>
  );
}

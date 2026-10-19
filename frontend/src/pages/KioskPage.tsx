import axios from "axios";
import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { apiBaseUrl } from "@/api/client";
import type { FaceEnrollmentStart, FaceIdentifyResult, KioskMe } from "@/api/types";
import { Button, Field } from "@/components/ui";
import { explainFaceError } from "@/face/errors";
import { errorMessage } from "@/lib/errors";
import { FaceCapture } from "@/face/FaceCapture";
import { ENROLL_KEY } from "@/face/FaceEnrollWizard";
import { FaceEnrollSteps } from "@/face/FaceEnrollSteps";
import { loginFace } from "@/face/faceAuthApi";
import { kioskSocketUrl } from "@/realtime/events";

const TOKEN_KEY = "attendance.kiosk.token";

function clientFor(token: string) {
  return axios.create({
    baseURL: apiBaseUrl,
    headers: { Authorization: `Bearer ${token}` },
  });
}

function chime(granted: boolean) {
  const Context =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Context) {
    return;
  }
  const audio = new Context();
  const oscillator = audio.createOscillator();
  const gain = audio.createGain();
  oscillator.frequency.value = granted ? 880 : 220;
  gain.gain.value = 0.04;
  oscillator.connect(gain);
  gain.connect(audio.destination);
  oscillator.start();
  oscillator.stop(audio.currentTime + 0.15);
}

export function KioskPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? "");
  const [draft, setDraft] = useState("");
  const [me, setMe] = useState<KioskMe | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FaceIdentifyResult | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [session, setSession] = useState<FaceEnrollmentStart | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [lookupName, setLookupName] = useState("");
  const online = typeof navigator === "undefined" ? true : navigator.onLine;
  const clock = useClock();

  useEffect(() => {
    if (!token) {
      return;
    }
    const http = clientFor(token);
    http
      .get<KioskMe>("/kiosk/me/")
      .then((response) => setMe(response.data))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken("");
        setError("El token del kiosco no es válido.");
      });
  }, [token]);

  useEffect(() => {
    if (!me) {
      return;
    }
    let lock: WakeLockSentinel | null = null;
    const request = () => {
      const wakeLock = navigator.wakeLock;
      if (!wakeLock) {
        return;
      }
      void wakeLock
        .request("screen")
        .then((sentinel) => {
          lock = sentinel;
        })
        .catch(() => undefined);
    };
    request();
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        request();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      void lock?.release();
    };
  }, [me]);

  useEffect(() => {
    if (!token || !me) {
      return;
    }
    const http = clientFor(token);
    const beat = () => {
      void readCameraPermission().then((permission) =>
        http.post("/kiosk/heartbeat/", { camera_permission: permission }).catch(() => undefined),
      );
    };
    beat();
    const timer = window.setInterval(beat, 30_000);
    return () => window.clearInterval(timer);
  }, [token, me]);

  useEffect(() => {
    if (!result) {
      return;
    }
    const timer = window.setTimeout(() => setResult(null), 3000);
    return () => window.clearTimeout(timer);
  }, [result]);

  const submitToken = useCallback(
    async (redirectToken: string) => {
      if (!token) {
        return;
      }
      setBusy(true);
      setError("");
      try {
        const response = await clientFor(token).post<FaceIdentifyResult>("/kiosk/face-identify/", {
          redirect_token: redirectToken,
        });
        setResult(response.data);
        chime(response.data.status === "GRANTED");
      } catch (caught) {
        setError(errorMessage(caught));
      } finally {
        setBusy(false);
      }
    },
    [token],
  );

  useEffect(() => {
    if (!location.pathname.endsWith("/callback")) {
      return;
    }
    const params = new URLSearchParams(location.search);
    const redirectToken = params.get("token") ?? "";
    window.history.replaceState({}, "", "/kiosk");
    if (redirectToken && token) {
      void submitToken(redirectToken);
    }
    navigate("/kiosk", { replace: true });
  }, [location.pathname, location.search, navigate, submitToken, token]);

  async function pair() {
    setError("");
    const next = draft.trim();
    if (!next) {
      setError("Pegue el token del kiosco.");
      return;
    }
    try {
      const response = await clientFor(next).get<KioskMe>("/kiosk/me/");
      localStorage.setItem(TOKEN_KEY, next);
      setToken(next);
      setMe(response.data);
      setDraft("");
    } catch {
      setError("No se pudo emparejar el kiosco.");
    }
  }

  async function onClip(clip: Blob) {
    if (!me?.app_id || !me.api_url) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const { redirectToken } = await loginFace(me.api_url, me.app_id, clip);
      await submitToken(redirectToken);
    } catch (caught) {
      setError(explainFaceError(caught).message);
      setBusy(false);
    }
  }

  async function startEnroll() {
    if (!token) {
      return;
    }
    setError("");
    try {
      const lookup = await clientFor(token).post<{ first_name: string; last_name: string }>(
        "/kiosk/employees/lookup/",
        { document_id: documentId.trim() },
      );
      setLookupName(`${lookup.data.first_name} ${lookup.data.last_name}`);
      const started = await clientFor(token).post<FaceEnrollmentStart>(
        "/kiosk/face-enrollment-sessions/",
        { document_id: documentId.trim() },
      );
      setSession(started.data);
      setEnrolling(true);
    } catch {
      setError("No encontramos ese documento o el registro no está habilitado.");
    }
  }

  function forget() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setMe(null);
  }

  if (!token || !me) {
    return (
      <main className="kiosk">
        <section className="kiosk-card">
          <p className="eyebrow">Kiosco</p>
          <h1>Emparejar puerta</h1>
          <p>Pegue el token que muestra el panel una sola vez.</p>
          {error ? <p className="face-error">{error}</p> : null}
          <Field label="Token">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              autoComplete="off"
            />
          </Field>
          <Button type="button" onClick={() => void pair()}>
            Conectar
          </Button>
        </section>
      </main>
    );
  }

  const granted = result?.status === "GRANTED";
  const captureEnabled = online && me.face_enabled && !busy && !result && !enrolling;

  return (
    <main className="kiosk">
      <section className="kiosk-card">
        <p className="eyebrow">{me.organization_name}</p>
        <h1>{me.door_name}</h1>
        <p className="kiosk-clock">
          <time>{clock}</time>
          {" · "}
          {online ? "En línea" : "Sin Internet"}
        </p>
        {me.camera_permission === "denied" ? (
          <p className="face-error">
            La cámara está bloqueada. En el candado de la barra de direcciones, permita la cámara y
            recargue la página.
          </p>
        ) : null}
        {error ? <p className="face-error">{error}</p> : null}
        {result ? (
          <div className={granted ? "kiosk-result granted" : "kiosk-result denied"}>
            <strong>{granted ? "Acceso concedido" : "Acceso denegado"}</strong>
            <p>{result.message}</p>
          </div>
        ) : null}
        {!captureEnabled && !result && !enrolling ? (
          <p className="kiosk-fallback">
            Use su tarjeta. El rostro no está disponible en este momento.
          </p>
        ) : null}
        {captureEnabled ? (
          <FaceCapture
            onClip={onClip}
            onUnsupported={() => {
              void clientFor(token)
                .get<{ url: string }>("/kiosk/faceauth/start/")
                .then((response) => window.location.assign(response.data.url));
            }}
          />
        ) : null}
        {me.allow_kiosk_self_enrollment && !enrolling && !result ? (
          <div className="stack">
            <Field label="Documento para registrar el rostro">
              <input value={documentId} onChange={(event) => setDocumentId(event.target.value)} />
            </Field>
            <Button type="button" variant="ghost" onClick={() => void startEnroll()}>
              Registrar mi rostro
            </Button>
            {lookupName ? <p>{lookupName}</p> : null}
          </div>
        ) : null}
        {enrolling && session ? (
          <FaceEnrollSteps
            session={session}
            onComplete={async (redirectToken) => {
              await clientFor(token).post(`/face-enrollment-sessions/${session.id}/complete/`, {
                redirect_token: redirectToken,
              });
              setEnrolling(false);
              setSession(null);
            }}
            onFail={async (code, message) => {
              await clientFor(token).post(`/face-enrollment-sessions/${session.id}/fail/`, {
                code,
                message,
              });
            }}
            onHosted={() => {
              sessionStorage.setItem(
                ENROLL_KEY,
                JSON.stringify({ sessionId: session.id, mode: "kiosk" }),
              );
              void clientFor(token)
                .get<{ url: string }>(`/face-enrollment-sessions/${session.id}/hosted-start/`)
                .then((response) => window.location.assign(response.data.url));
            }}
          />
        ) : null}
        <KioskSocket token={token} onResult={setResult} />
        <button
          type="button"
          className="linkish"
          onClick={() => void document.documentElement.requestFullscreen?.()}
        >
          Pantalla completa
        </button>
        <button type="button" className="linkish" onClick={forget}>
          Olvidar este kiosco
        </button>
      </section>
    </main>
  );
}

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return now.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
}

async function readCameraPermission(): Promise<"granted" | "denied" | "prompt" | "unknown"> {
  try {
    const status = await navigator.permissions.query({ name: "camera" as PermissionName });
    if (status.state === "granted" || status.state === "denied" || status.state === "prompt") {
      return status.state;
    }
  } catch {
    return "unknown";
  }
  return "unknown";
}

function KioskSocket({
  token,
  onResult,
}: {
  token: string;
  onResult: (result: FaceIdentifyResult) => void;
}) {
  useEffect(() => {
    if (import.meta.env.MODE === "test") {
      return;
    }
    let socket: WebSocket | null = null;
    let stopped = false;
    let attempt = 0;
    let timer = 0;
    const connect = () => {
      socket = new WebSocket(kioskSocketUrl());
      socket.onopen = () => {
        attempt = 0;
        socket?.send(JSON.stringify({ op: "auth", token }));
      };
      socket.onmessage = (event) => {
        const body = JSON.parse(String(event.data)) as {
          event?: string;
          data?: FaceIdentifyResult & { request_id?: string };
        };
        if (body.event === "face.result" && body.data?.request_id) {
          onResult({
            id: body.data.request_id,
            status: body.data.status,
            code: body.data.code,
            message: body.data.message,
            door_id: body.data.door_id,
            kiosk_id: body.data.kiosk_id,
            log_id: body.data.log_id,
          });
          chime(body.data.status === "GRANTED");
        }
      };
      socket.onclose = () => {
        if (stopped) {
          return;
        }
        attempt += 1;
        timer = window.setTimeout(connect, Math.min(10_000, 500 * 2 ** attempt));
      };
    };
    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [token, onResult]);
  return null;
}

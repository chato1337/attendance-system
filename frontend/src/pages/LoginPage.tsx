import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate } from "react-router-dom";
import { z } from "zod";

import axios from "axios";

import { api, apiBaseUrl } from "@/api/client";
import type { FaceLoginOptions, TokenPair } from "@/api/types";
import { useSession } from "@/auth/session";
import { Banner, Button, Field } from "@/components/ui";
import { APP_TITLE } from "@/content";
import { explainFaceError } from "@/face/errors";
import { FaceCapture } from "@/face/FaceCapture";
import { FaceAuthRequestError, loginFace } from "@/face/faceAuthApi";
import { errorMessage } from "@/lib/errors";

const schema = z.object({
  username: z.string().trim().min(1, "Indique el usuario."),
  password: z.string().min(1, "Indique la contraseña."),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const access = useSession((state) => state.access);
  const hydrated = useSession((state) => state.hydrated);
  const applyTokens = useSession((state) => state.applyTokens);
  const setUser = useSession((state) => state.setUser);
  const clear = useSession((state) => state.clear);
  const [error, setError] = useState("");
  const [slug, setSlug] = useState("");
  const [faceOptions, setFaceOptions] = useState<FaceLoginOptions | null>(null);
  const [faceError, setFaceError] = useState("");
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });

  if (!hydrated) {
    return <p className="boot">Cargando…</p>;
  }
  if (access) {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(values: FormValues) {
    setError("");
    try {
      const tokens = await api.login(values.username, values.password);
      applyTokens(tokens);
      const user = await api.me();
      setUser(user);
    } catch (caught) {
      clear();
      if (
        typeof caught === "object" &&
        caught &&
        "response" in caught &&
        (caught as { response?: { status?: number } }).response?.status === 401
      ) {
        setError("Usuario o contraseña incorrectos.");
        return;
      }
      setError(errorMessage(caught));
    }
  }

  return (
    <main className="gate">
      <section className="gate-card">
        <p className="eyebrow">Attendance System</p>
        <h1>{APP_TITLE}</h1>
        <p>Entre con el usuario de su organización.</p>
        <form className="form-grid" onSubmit={form.handleSubmit(onSubmit)}>
          {error ? <Banner>{error}</Banner> : null}
          <Field label="Usuario" error={form.formState.errors.username?.message}>
            <input {...form.register("username")} autoComplete="username" />
          </Field>
          <Field label="Contraseña" error={form.formState.errors.password?.message}>
            <input type="password" {...form.register("password")} autoComplete="current-password" />
          </Field>
          <Button type="submit" disabled={form.formState.isSubmitting}>
            Entrar
          </Button>
        </form>
        <div className="stack">
          <h2>Ingresar con rostro</h2>
          <Field label="Organización">
            <input
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              placeholder="acme"
            />
          </Field>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setFaceError("");
              void axios
                .get<FaceLoginOptions>(`${apiBaseUrl}/auth/faceauth/options/`, {
                  params: { org_slug: slug.trim() },
                })
                .then((response) => {
                  setFaceOptions(response.data);
                  if (!response.data.allow_panel_login) {
                    setFaceError("Esa organización no permite ingresar con rostro.");
                  }
                })
                .catch((caught) => setFaceError(errorMessage(caught)));
            }}
          >
            Continuar
          </Button>
          {faceError ? <Banner>{faceError}</Banner> : null}
          {faceOptions?.allow_panel_login && faceOptions.api_url && faceOptions.app_id ? (
            <FaceCapture
              onUnsupported={() => {
                sessionStorage.setItem("face.org", slug.trim());
                void axios
                  .get<{ url: string }>(`${apiBaseUrl}/auth/faceauth/start/`, {
                    params: { org_slug: slug.trim() },
                  })
                  .then((response) => window.location.assign(response.data.url));
              }}
              onClip={async (clip) => {
                setFaceError("");
                try {
                  const { redirectToken } = await loginFace(
                    faceOptions.api_url ?? "",
                    faceOptions.app_id ?? "",
                    clip,
                  );
                  const response = await axios.post<TokenPair>(
                    `${apiBaseUrl}/auth/faceauth/callback/`,
                    { redirect_token: redirectToken, org_slug: slug.trim() },
                  );
                  applyTokens(response.data);
                  setUser(await api.me());
                } catch (caught) {
                  setFaceError(
                    caught instanceof FaceAuthRequestError
                      ? explainFaceError(caught).message
                      : errorMessage(caught),
                  );
                }
              }}
            />
          ) : null}
        </div>
      </section>
    </main>
  );
}

import { useState } from "react";

import { Button, Field } from "@/components/ui";

import type { FaceEnrollmentStart } from "@/api/types";
import { explainFaceError } from "./errors";
import { FaceCapture } from "./FaceCapture";
import { registerFace, requestOtp, verifyOtp } from "./faceAuthApi";

type Props = {
  session: FaceEnrollmentStart;
  onComplete: (redirectToken: string) => Promise<void>;
  onFail: (code: string, message: string) => Promise<void>;
  onHosted?: () => void;
};

export function FaceEnrollSteps({ session, onComplete, onFail, onHosted }: Props) {
  const [phase, setPhase] = useState<"otp" | "code" | "capture" | "done">("otp");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function sendCode() {
    setBusy(true);
    setError("");
    try {
      await requestOtp(session.api_url, session.app_id, {
        email: session.email,
        first_name: session.first_name,
        last_name: session.last_name,
      });
      setPhase("code");
    } catch (caught) {
      setError(explainFaceError(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function checkCode() {
    setBusy(true);
    setError("");
    try {
      await verifyOtp(session.api_url, session.app_id, session.email, code.trim());
      setPhase("capture");
    } catch (caught) {
      setError(explainFaceError(caught).message);
    } finally {
      setBusy(false);
    }
  }

  async function enroll(clip: Blob) {
    setBusy(true);
    setError("");
    try {
      const { redirectToken } = await registerFace(
        session.api_url,
        session.app_id,
        {
          email: session.email,
          first_name: session.first_name,
          last_name: session.last_name,
        },
        code.trim(),
        clip,
      );
      await onComplete(redirectToken);
      setPhase("done");
    } catch (caught) {
      const explained = explainFaceError(caught);
      setError(explained.message);
      if (!explained.recaptureOnly && caught instanceof Error) {
        const codeName =
          "code" in caught && typeof caught.code === "string" ? caught.code : "register_failed";
        await onFail(codeName, explained.message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <p>
        El código llega a <strong>{session.email}</strong>. El video no pasa por este sistema.
      </p>
      {error ? <p className="face-error">{error}</p> : null}
      {phase === "otp" ? (
        <Button type="button" onClick={() => void sendCode()} disabled={busy}>
          Enviar código
        </Button>
      ) : null}
      {phase === "code" ? (
        <>
          <Field label="Código del correo">
            <input
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
            />
          </Field>
          <Button
            type="button"
            onClick={() => void checkCode()}
            disabled={busy || code.trim().length < 4}
          >
            Validar código
          </Button>
        </>
      ) : null}
      {phase === "capture" ? (
        <FaceCapture disabled={busy} onClip={enroll} onUnsupported={onHosted} />
      ) : null}
      {phase === "done" ? <p>Rostro registrado.</p> : null}
    </div>
  );
}

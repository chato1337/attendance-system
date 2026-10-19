import { useEffect, useState } from "react";

import { api } from "@/api/client";
import type { Employee, FaceEnrollmentStart } from "@/api/types";
import { Button, Modal } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { personName } from "@/lib/labels";

import { FaceEnrollSteps } from "./FaceEnrollSteps";

const ENROLL_KEY = "face.enroll";

export function FaceEnrollWizard({
  employee,
  onClose,
}: {
  employee: Employee;
  onClose: () => void;
}) {
  const [session, setSession] = useState<FaceEnrollmentStart | null>(null);
  const [error, setError] = useState("");
  const [shared, setShared] = useState("");

  useEffect(() => {
    let active = true;
    api
      .create<FaceEnrollmentStart>(`/employees/${employee.id}/face-enrollment-sessions/`)
      .then((started) => {
        if (active) {
          setSession(started);
        }
      })
      .catch((caught) => {
        if (active) {
          setError(errorMessage(caught));
        }
      });
    return () => {
      active = false;
    };
  }, [employee.id]);

  async function copyLink() {
    if (!session) {
      return;
    }
    const link = `${window.location.origin}/enrolar/${session.id}`;
    setShared(link);
    try {
      await navigator.clipboard.writeText(link);
    } catch {
      setShared(link);
    }
  }

  async function hosted() {
    if (!session) {
      return;
    }
    const start = await api.get<{ url: string }>(
      `/face-enrollment-sessions/${session.id}/hosted-start/`,
    );
    sessionStorage.setItem(ENROLL_KEY, JSON.stringify({ sessionId: session.id, mode: "panel" }));
    window.location.assign(start.url);
  }

  return (
    <Modal title={`Enrolar rostro · ${personName(employee)}`} onClose={onClose}>
      {error ? <p className="face-error">{error}</p> : null}
      {!session && !error ? <p>Preparando la sesión…</p> : null}
      {session ? (
        <FaceEnrollSteps
          session={session}
          onHosted={() => void hosted()}
          onComplete={async (redirectToken) => {
            await api.create(`/face-enrollment-sessions/${session.id}/complete/`, {
              redirect_token: redirectToken,
            });
          }}
          onFail={async (code, message) => {
            await api.create(`/face-enrollment-sessions/${session.id}/fail/`, { code, message });
          }}
        />
      ) : null}
      {session ? (
        <Button type="button" variant="ghost" onClick={() => void copyLink()}>
          Copiar enlace para otro dispositivo
        </Button>
      ) : null}
      {shared ? (
        <p>
          Quien tenga sesión en el panel puede abrir <code>{shared}</code>. El enlace caduca con la
          sesión, a los 15 minutos.
        </p>
      ) : null}
      <Button type="button" variant="ghost" onClick={onClose}>
        Cerrar
      </Button>
    </Modal>
  );
}

export { ENROLL_KEY };

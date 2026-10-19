import { useParams } from "react-router-dom";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { FaceEnrollmentStart } from "@/api/types";
import { Banner, Loading, Page } from "@/components/ui";
import { FaceEnrollSteps } from "@/face/FaceEnrollSteps";
import { errorMessage } from "@/lib/errors";

export function FaceEnrollPage() {
  const { sessionId = "" } = useParams();
  const session = useOrgQuery(["/face-enrollment-sessions/", sessionId], () =>
    api.get<FaceEnrollmentStart>(`/face-enrollment-sessions/${sessionId}/`),
  );

  const current = session.data;

  return (
    <Page
      title="Enrolar rostro"
      lede="Este enlace vale para la sesión abierta. El video se envía a Face-Auth, no a esta instalación."
    >
      {session.isLoading ? <Loading /> : null}
      {session.isError ? <Banner>{errorMessage(session.error)}</Banner> : null}
      {current ? (
        <FaceEnrollSteps
          session={current}
          onComplete={async (redirectToken) => {
            await api.create(`/face-enrollment-sessions/${current.id}/complete/`, {
              redirect_token: redirectToken,
            });
          }}
          onFail={async (code, message) => {
            await api.create(`/face-enrollment-sessions/${current.id}/fail/`, {
              code,
              message,
            });
          }}
        />
      ) : null}
    </Page>
  );
}

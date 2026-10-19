import { useEffect, useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type {
  Credential,
  Door,
  EdgeCommand,
  Employee,
  EnrollmentRead,
  Reader,
  ReaderProfile,
} from "@/api/types";
import { usePreferences } from "@/auth/preferences";
import { Banner, Button, Empty, Field, Loading, Page } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { COMMAND_STATUS_LABEL, CREDENTIAL_TYPE_LABEL, personName } from "@/lib/labels";
import { formatStamp } from "@/lib/time";

export function EnrollmentPage() {
  const timeZone = usePreferences((state) => state.timeZone);
  const [readerId, setReaderId] = useState("");
  const [seconds, setSeconds] = useState(60);
  const [nodeId, setNodeId] = useState("");
  const [command, setCommand] = useState<EdgeCommand | null>(null);
  const [employeeId, setEmployeeId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const readers = useOrgQuery(["/readers/", "enroll"], () =>
    api.list<Reader>("/readers/", { page_size: 100, is_active: true }),
  );
  const doors = useOrgQuery(["/doors/", "lookup"], () =>
    api.list<Door>("/doors/", { page_size: 100 }),
  );
  const profiles = useOrgQuery(["/reader-profiles/", "lookup"], () =>
    api.list<ReaderProfile>("/reader-profiles/", { page_size: 100 }),
  );
  const employees = useOrgQuery(["/employees/", "lookup"], () =>
    api.list<Employee>("/employees/", { page_size: 100, is_active: true, ordering: "last_name" }),
  );
  const reads = useOrgQuery(
    ["/enrollment-reads/", readerId, command?.id ?? ""],
    () =>
      api.get<EnrollmentRead[]>("/enrollment-reads/", {
        reader: readerId,
        command: command?.id,
      }),
    { enabled: Boolean(readerId), refetchInterval: command ? 2000 : false },
  );
  const commandState = useOrgQuery(
    ["/commands/", command?.id ?? ""],
    () => api.get<EdgeCommand>(`/nodes/${nodeId}/commands/${command?.id}/`),
    {
      enabled: Boolean(command && nodeId),
      refetchInterval: command && !isTerminal(command.status) ? 2000 : false,
    },
  );

  const reader = readers.data?.results.find((item) => item.id === readerId) ?? null;
  const door = doors.data?.results.find((item) => item.id === reader?.door);
  const profile = profiles.data?.results.find((item) => item.id === reader?.reader_profile);
  const liveCommand = commandState.data ?? command;

  useEffect(() => {
    if (commandState.data) {
      setCommand(commandState.data);
    }
  }, [commandState.data]);

  async function start() {
    if (!reader || !door) {
      setError("Elija un lector.");
      return;
    }
    setError("");
    setNotice("");
    try {
      const created = await api.create<EdgeCommand>(`/nodes/${door.node}/commands/`, {
        type: "enrollment_mode",
        payload: { reader_id: reader.id, seconds },
        wait: 0,
      });
      setNodeId(door.node);
      setCommand(created);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function assign(read: EnrollmentRead) {
    if (!reader || !employeeId || !read.payload) {
      setError("Elija el empleado y una lectura con identificador.");
      return;
    }
    const type = read.credential_type || profile?.credential_type || "RFID";
    setError("");
    try {
      await api.create<Credential>("/credentials/", {
        employee: employeeId,
        type,
        payload: read.payload,
        source: "ASSISTED_ENROLLMENT",
        reader_profile: reader.reader_profile,
        is_active: true,
      });
      setNotice("Credencial asignada. El agente la recibirá en el siguiente delta.");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Enrolamiento asistido"
      lede="Durante unos segundos el lector reporta lecturas sin abrir la puerta. Asigne el identificador normalizado a un empleado."
    >
      {error ? <Banner>{error}</Banner> : null}
      {notice ? <Banner tone="ok">{notice}</Banner> : null}
      <div className="filters">
        <Field label="Lector">
          <select value={readerId} onChange={(event) => setReaderId(event.target.value)}>
            <option value="">Elegir</option>
            {readers.data?.results.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.reader_device_id}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Segundos">
          <input
            type="number"
            min={1}
            max={600}
            value={seconds}
            onChange={(event) => setSeconds(Number(event.target.value))}
          />
        </Field>
        <Button type="button" onClick={() => void start()} disabled={!readerId}>
          Iniciar enrolamiento
        </Button>
      </div>
      {liveCommand ? (
        <Banner tone="info">
          Modo de enrolamiento: {COMMAND_STATUS_LABEL[liveCommand.status] ?? liveCommand.status}
        </Banner>
      ) : null}
      {reads.isLoading ? <Loading /> : null}
      {(reads.data?.length ?? 0) === 0 && readerId && !reads.isLoading ? (
        <Empty>Aún no llegan lecturas de este lector.</Empty>
      ) : null}
      {(reads.data?.length ?? 0) > 0 ? (
        <>
          <Field label="Asignar a">
            <select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}>
              <option value="">Elegir empleado</option>
              {employees.data?.results.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {personName(employee)} · {employee.document_id}
                </option>
              ))}
            </select>
          </Field>
          <div className="table-wrap">
            <table className="grid">
              <caption className="sr-only">Lecturas</caption>
              <thead>
                <tr>
                  <th>Hora</th>
                  <th>Crudo</th>
                  <th>Normalizado</th>
                  <th>Tipo</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {reads.data?.map((read) => (
                  <tr key={read.id}>
                    <td>{formatStamp(read.created_at, timeZone)}</td>
                    <td>
                      <code>{read.raw || "—"}</code>
                    </td>
                    <td>
                      <code>{read.payload || "—"}</code>
                      {read.error ? <small>{read.error}</small> : null}
                    </td>
                    <td>
                      {CREDENTIAL_TYPE_LABEL[read.credential_type] ?? (read.credential_type || "—")}
                    </td>
                    <td>
                      {read.payload && !read.error ? (
                        <Button type="button" variant="ghost" onClick={() => void assign(read)}>
                          Asignar
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </Page>
  );
}

function isTerminal(status: string): boolean {
  return status === "ACKED" || status === "FAILED" || status === "EXPIRED";
}

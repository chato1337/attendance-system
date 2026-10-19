import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { Department, Employee, Holiday, Shift, WorkSchedule } from "@/api/types";
import { useSession } from "@/auth/session";
import { Badge, Banner, Button, Empty, Field, Loading, Page } from "@/components/ui";
import { errorMessage } from "@/lib/errors";
import { WEEKDAY_LABEL, personName } from "@/lib/labels";

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7];

function clock(value: string): string {
  return value.slice(0, 5);
}

function weekdayText(days: number[]): string {
  return days.map((day) => WEEKDAY_LABEL[day] ?? String(day)).join(" ");
}

export function SchedulesPage({ canEdit }: { canEdit: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const shifts = useOrgQuery(["/shifts/"], () =>
    api.list<Shift>("/shifts/", { page_size: 100, ordering: "name" }),
  );
  const schedules = useOrgQuery(["/schedules/"], () =>
    api.list<WorkSchedule>("/schedules/", { page_size: 100, ordering: "-updated_at" }),
  );
  const holidays = useOrgQuery(["/holidays/"], () =>
    api.list<Holiday>("/holidays/", { page_size: 100, ordering: "-date" }),
  );
  const departments = useOrgQuery(["/departments/", "lookup"], () =>
    api.list<Department>("/departments/", { page_size: 100, ordering: "name", is_active: true }),
  );
  const employees = useOrgQuery(["/employees/", "lookup"], () =>
    api.list<Employee>("/employees/", { page_size: 100, ordering: "last_name", is_active: true }),
  );

  const [shiftForm, setShiftForm] = useState({
    name: "",
    start_time: "08:00",
    end_time: "17:00",
    late_tolerance_minutes: "10",
    early_leave_tolerance_minutes: "10",
  });
  const [target, setTarget] = useState<"department" | "employee">("department");
  const [scheduleForm, setScheduleForm] = useState({
    shift: "",
    department: "",
    employee: "",
    weekdays: [1, 2, 3, 4, 5] as number[],
  });
  const [holidayForm, setHolidayForm] = useState({ date: "", name: "" });

  async function refresh(path: string) {
    await queryClient.invalidateQueries({ queryKey: [organizationId, path] });
  }

  async function createShift() {
    setError("");
    if (shiftForm.end_time <= shiftForm.start_time) {
      setError("El turno termina el mismo día, después de la hora de entrada.");
      return;
    }
    try {
      await api.create("/shifts/", {
        ...shiftForm,
        late_tolerance_minutes: Number(shiftForm.late_tolerance_minutes),
        early_leave_tolerance_minutes: Number(shiftForm.early_leave_tolerance_minutes),
        is_active: true,
      });
      setShiftForm({ ...shiftForm, name: "" });
      await refresh("/shifts/");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  function toggleDay(day: number) {
    setScheduleForm((current) => ({
      ...current,
      weekdays: current.weekdays.includes(day)
        ? current.weekdays.filter((item) => item !== day)
        : [...current.weekdays, day].sort((a, b) => a - b),
    }));
  }

  async function createSchedule() {
    setError("");
    if (!scheduleForm.shift || scheduleForm.weekdays.length === 0) {
      setError("Elija un turno y al menos un día.");
      return;
    }
    const body =
      target === "department"
        ? {
            shift: scheduleForm.shift,
            department: scheduleForm.department,
            weekdays: scheduleForm.weekdays,
          }
        : {
            shift: scheduleForm.shift,
            employee: scheduleForm.employee,
            weekdays: scheduleForm.weekdays,
          };
    if (target === "department" && !scheduleForm.department) {
      setError("Elija el departamento.");
      return;
    }
    if (target === "employee" && !scheduleForm.employee) {
      setError("Elija el empleado.");
      return;
    }
    try {
      await api.create("/schedules/", body);
      await refresh("/schedules/");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function createHoliday() {
    setError("");
    try {
      await api.create("/holidays/", holidayForm);
      setHolidayForm({ date: "", name: "" });
      await refresh("/holidays/");
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function deactivate(path: string, id: string) {
    setError("");
    try {
      await api.remove(`${path}${id}/`);
      await refresh(path);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  const loading = shifts.isLoading || schedules.isLoading || holidays.isLoading;

  return (
    <Page
      title="Horarios"
      lede="El turno del empleado prevalece sobre el de su departamento. Un festivo no cuenta como ausencia."
    >
      {error ? <Banner>{error}</Banner> : null}
      {loading ? <Loading /> : null}
      <div className="stack">
        <section className="card">
          <h2>Turnos</h2>
          {(shifts.data?.results.length ?? 0) === 0 ? (
            <Empty>Todavía no hay turnos.</Empty>
          ) : (
            <table className="grid">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Entrada</th>
                  <th>Salida</th>
                  <th>Tolerancia</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {shifts.data?.results.map((shift) => (
                  <tr key={shift.id}>
                    <td>
                      {shift.name}{" "}
                      {shift.is_active ? null : <Badge tone="off">Inactivo</Badge>}
                    </td>
                    <td>{clock(shift.start_time)}</td>
                    <td>{clock(shift.end_time)}</td>
                    <td>
                      {shift.late_tolerance_minutes} / {shift.early_leave_tolerance_minutes} min
                    </td>
                    <td>
                      {canEdit && shift.is_active ? (
                        <Button
                          variant="ghost"
                          type="button"
                          onClick={() => void deactivate("/shifts/", shift.id)}
                        >
                          Desactivar
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canEdit ? (
            <div className="filters">
              <Field label="Nombre">
                <input
                  value={shiftForm.name}
                  onChange={(event) => setShiftForm({ ...shiftForm, name: event.target.value })}
                />
              </Field>
              <Field label="Entrada">
                <input
                  type="time"
                  value={shiftForm.start_time}
                  onChange={(event) =>
                    setShiftForm({ ...shiftForm, start_time: event.target.value })
                  }
                />
              </Field>
              <Field label="Salida">
                <input
                  type="time"
                  value={shiftForm.end_time}
                  onChange={(event) => setShiftForm({ ...shiftForm, end_time: event.target.value })}
                />
              </Field>
              <Field label="Tolerancia de entrada">
                <input
                  type="number"
                  min={0}
                  max={240}
                  value={shiftForm.late_tolerance_minutes}
                  onChange={(event) =>
                    setShiftForm({ ...shiftForm, late_tolerance_minutes: event.target.value })
                  }
                />
              </Field>
              <Field label="Tolerancia de salida">
                <input
                  type="number"
                  min={0}
                  max={240}
                  value={shiftForm.early_leave_tolerance_minutes}
                  onChange={(event) =>
                    setShiftForm({
                      ...shiftForm,
                      early_leave_tolerance_minutes: event.target.value,
                    })
                  }
                />
              </Field>
              <Button type="button" onClick={() => void createShift()} disabled={!shiftForm.name}>
                Agregar turno
              </Button>
            </div>
          ) : null}
        </section>

        <section className="card">
          <h2>Asignaciones</h2>
          <p className="hint">
            Si dos horarios cubren el mismo día, se usa el que se actualizó más recientemente.
          </p>
          {(schedules.data?.results.length ?? 0) === 0 ? (
            <Empty>Nadie tiene horario todavía.</Empty>
          ) : (
            <table className="grid">
              <thead>
                <tr>
                  <th>Aplica a</th>
                  <th>Turno</th>
                  <th>Días</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {schedules.data?.results.map((schedule) => (
                  <tr key={schedule.id}>
                    <td>
                      {schedule.employee_name || schedule.department_name}{" "}
                      {schedule.is_active ? null : <Badge tone="off">Inactivo</Badge>}
                    </td>
                    <td>{schedule.shift_name}</td>
                    <td>{weekdayText(schedule.weekdays)}</td>
                    <td>
                      {canEdit && schedule.is_active ? (
                        <Button
                          variant="ghost"
                          type="button"
                          onClick={() => void deactivate("/schedules/", schedule.id)}
                        >
                          Desactivar
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canEdit ? (
            <div className="filters">
              <Field label="Turno">
                <select
                  value={scheduleForm.shift}
                  onChange={(event) =>
                    setScheduleForm({ ...scheduleForm, shift: event.target.value })
                  }
                >
                  <option value="">Elegir</option>
                  {shifts.data?.results
                    .filter((shift) => shift.is_active)
                    .map((shift) => (
                      <option key={shift.id} value={shift.id}>
                        {shift.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label="Destino">
                <select
                  value={target}
                  onChange={(event) => setTarget(event.target.value as "department" | "employee")}
                >
                  <option value="department">Departamento</option>
                  <option value="employee">Empleado</option>
                </select>
              </Field>
              {target === "department" ? (
                <Field label="Departamento">
                  <select
                    value={scheduleForm.department}
                    onChange={(event) =>
                      setScheduleForm({ ...scheduleForm, department: event.target.value })
                    }
                  >
                    <option value="">Elegir</option>
                    {departments.data?.results.map((department) => (
                      <option key={department.id} value={department.id}>
                        {department.name}
                      </option>
                    ))}
                  </select>
                </Field>
              ) : (
                <Field label="Empleado">
                  <select
                    value={scheduleForm.employee}
                    onChange={(event) =>
                      setScheduleForm({ ...scheduleForm, employee: event.target.value })
                    }
                  >
                    <option value="">Elegir</option>
                    {employees.data?.results.map((employee) => (
                      <option key={employee.id} value={employee.id}>
                        {personName(employee)}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              <div className="weekday-picks" role="group" aria-label="Días">
                {WEEKDAYS.map((day) => (
                  <button
                    key={day}
                    type="button"
                    className={scheduleForm.weekdays.includes(day) ? "on" : ""}
                    aria-pressed={scheduleForm.weekdays.includes(day)}
                    onClick={() => toggleDay(day)}
                  >
                    {WEEKDAY_LABEL[day]}
                  </button>
                ))}
              </div>
              <Button type="button" onClick={() => void createSchedule()}>
                Asignar horario
              </Button>
            </div>
          ) : null}
        </section>

        <section className="card">
          <h2>Festivos</h2>
          {(holidays.data?.results.length ?? 0) === 0 ? (
            <Empty>No hay festivos cargados.</Empty>
          ) : (
            <table className="grid">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Nombre</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {holidays.data?.results.map((holiday) => (
                  <tr key={holiday.id}>
                    <td>{holiday.date}</td>
                    <td>{holiday.name}</td>
                    <td>
                      {canEdit ? (
                        <Button
                          variant="ghost"
                          type="button"
                          onClick={() => void deactivate("/holidays/", holiday.id)}
                        >
                          Quitar
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canEdit ? (
            <div className="filters">
              <Field label="Fecha">
                <input
                  type="date"
                  value={holidayForm.date}
                  onChange={(event) => setHolidayForm({ ...holidayForm, date: event.target.value })}
                />
              </Field>
              <Field label="Nombre">
                <input
                  value={holidayForm.name}
                  onChange={(event) => setHolidayForm({ ...holidayForm, name: event.target.value })}
                />
              </Field>
              <Button
                type="button"
                onClick={() => void createHoliday()}
                disabled={!holidayForm.date || !holidayForm.name}
              >
                Agregar festivo
              </Button>
            </div>
          ) : null}
        </section>
      </div>
    </Page>
  );
}

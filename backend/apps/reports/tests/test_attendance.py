from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db.models import Sum
from django.utils import timezone

from apps.access.models import AccessLog, AccessStatus, Direction
from apps.people.models import Department, Employee
from apps.reports.engine import calculate_attendance
from apps.reports.models import AttendanceStatus, DailyAttendance, Holiday, Schedule, Shift
from apps.reports.tasks import rebuild_daily_attendance

TZ = ZoneInfo("America/Bogota")
MONDAY = date(2026, 3, 2)


def _at(day, hour, minute):
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)


def _employee(organization, document_id, department, first_name="Ana"):
    return Employee.all_objects.create(
        organization=organization,
        department=department,
        document_id=document_id,
        first_name=first_name,
        last_name="Ruiz",
    )


def _shift(organization, name="Diurna", start=(8, 0), end=(17, 0), late=10, early=10):
    return Shift.all_objects.create(
        organization=organization,
        name=name,
        start_time=time(*start),
        end_time=time(*end),
        late_tolerance_minutes=late,
        early_leave_tolerance_minutes=early,
    )


def _department_schedule(organization, department, shift, weekdays=None):
    return Schedule.all_objects.create(
        organization=organization,
        department=department,
        shift=shift,
        weekdays=weekdays or [1, 2, 3, 4, 5],
    )


def _log(organization, node, employee, moment, direction, status=AccessStatus.GRANTED):
    return AccessLog(
        organization=organization,
        node=node,
        employee=employee,
        timestamp=moment,
        direction=direction,
        status=status,
    )


@pytest.fixture
def operations(acme):
    return Department.all_objects.create(organization=acme, name="Operaciones")


def test_manual_day_matches_tolerances_orphan_and_absence(acme, acme_node, operations):
    """08:12–16:40 con tolerancia 10: 2 min tarde, 10 anticipados, 508 trabajados."""
    shift = _shift(acme)
    _department_schedule(acme, operations, shift)
    ana = _employee(acme, "A-1", operations, "Ana")
    luis = _employee(acme, "A-2", operations, "Luis")
    marta = _employee(acme, "A-3", operations, "Marta")
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, ana, _at(MONDAY, 8, 12), Direction.IN),
            _log(acme, acme_node, ana, _at(MONDAY, 16, 40), Direction.OUT),
            _log(acme, acme_node, luis, _at(MONDAY, 8, 0), Direction.IN),
        ]
    )

    assert calculate_attendance(acme, MONDAY, MONDAY) == 3

    ana_day = DailyAttendance.all_objects.get(employee=ana)
    assert ana_day.status == AttendanceStatus.LATE
    assert ana_day.late_minutes == 2
    assert ana_day.early_leave_minutes == 10
    assert ana_day.worked_minutes == 508
    assert ana_day.site == "Sede"
    assert ana_day.orphan_in is False

    luis_day = DailyAttendance.all_objects.get(employee=luis)
    assert luis_day.status == AttendanceStatus.INCOMPLETE
    assert luis_day.worked_minutes == 0
    assert luis_day.late_minutes == 0
    assert luis_day.orphan_in is True

    marta_day = DailyAttendance.all_objects.get(employee=marta)
    assert marta_day.status == AttendanceStatus.ABSENT
    assert marta_day.site == ""
    assert marta_day.worked_minutes == 0


def test_pairing_keeps_the_open_stay(acme, acme_node, operations):
    shift = _shift(acme, late=0, early=0)
    _department_schedule(acme, operations, shift)
    ana = _employee(acme, "P-1", operations)
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, ana, _at(MONDAY, 7, 50), Direction.OUT),
            _log(acme, acme_node, ana, _at(MONDAY, 8, 0), Direction.IN),
            _log(acme, acme_node, ana, _at(MONDAY, 9, 0), Direction.IN),
            _log(acme, acme_node, ana, _at(MONDAY, 17, 0), Direction.OUT),
        ]
    )
    calculate_attendance(acme, MONDAY, MONDAY)
    row = DailyAttendance.all_objects.get(employee=ana)
    assert row.worked_minutes == 540
    assert row.status == AttendanceStatus.PRESENT
    assert row.granted_count == 4


def test_employee_schedule_overrides_the_department(acme, acme_node, operations):
    department_shift = _shift(acme, name="Depto", late=10, early=10)
    personal_shift = _shift(acme, name="Personal", start=(9, 0), end=(18, 0), late=0, early=0)
    _department_schedule(acme, operations, department_shift)
    ana = _employee(acme, "O-1", operations)
    Schedule.all_objects.create(
        organization=acme,
        employee=ana,
        shift=personal_shift,
        weekdays=[1, 2, 3, 4, 5],
    )
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, ana, _at(MONDAY, 8, 30), Direction.IN),
            _log(acme, acme_node, ana, _at(MONDAY, 17, 30), Direction.OUT),
        ]
    )
    calculate_attendance(acme, MONDAY, MONDAY)
    row = DailyAttendance.all_objects.get(employee=ana)
    assert row.expected_start == time(9, 0)
    assert row.expected_end == time(18, 0)
    assert row.late_minutes == 0
    assert row.early_leave_minutes == 30
    assert row.worked_minutes == 540
    assert row.status == AttendanceStatus.EARLY_LEAVE


def test_holiday_cancels_absence_and_lateness(acme, acme_node, operations):
    shift = _shift(acme, late=0, early=0)
    _department_schedule(acme, operations, shift)
    Holiday.all_objects.create(organization=acme, date=MONDAY, name="Puente")
    came = _employee(acme, "H-1", operations, "Came")
    stayed = _employee(acme, "H-2", operations, "Stayed")
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, came, _at(MONDAY, 10, 0), Direction.IN),
            _log(acme, acme_node, came, _at(MONDAY, 12, 0), Direction.OUT),
        ]
    )
    calculate_attendance(acme, MONDAY, MONDAY)
    came_day = DailyAttendance.all_objects.get(employee=came)
    assert came_day.status == AttendanceStatus.PRESENT
    assert came_day.is_holiday is True
    assert came_day.late_minutes == 0
    assert came_day.worked_minutes == 120
    stayed_day = DailyAttendance.all_objects.get(employee=stayed)
    assert stayed_day.status == AttendanceStatus.HOLIDAY
    assert stayed_day.worked_minutes == 0


def test_denied_reads_and_inactive_people_do_not_count(acme, acme_node, operations):
    shift = _shift(acme)
    _department_schedule(acme, operations, shift)
    active = _employee(acme, "D-1", operations)
    inactive = _employee(acme, "D-2", operations, "Inactivo")
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])
    AccessLog.all_objects.create(
        organization=acme,
        node=acme_node,
        employee=active,
        timestamp=_at(MONDAY, 8, 0),
        direction=Direction.IN,
        status=AccessStatus.DENIED,
    )
    calculate_attendance(acme, MONDAY, MONDAY)
    assert DailyAttendance.all_objects.get(employee=active).status == AttendanceStatus.ABSENT
    assert not DailyAttendance.all_objects.filter(employee=inactive).exists()


def test_unscheduled_day_without_punches_is_not_stored(acme, acme_node, operations):
    shift = _shift(acme)
    _department_schedule(acme, operations, shift, weekdays=[1])
    ana = _employee(acme, "W-1", operations)
    saturday = date(2026, 3, 7)
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, ana, _at(saturday, 9, 0), Direction.IN),
            _log(acme, acme_node, ana, _at(saturday, 12, 0), Direction.OUT),
        ]
    )
    calculate_attendance(acme, saturday, saturday)
    row = DailyAttendance.all_objects.get(employee=ana, work_date=saturday)
    assert row.scheduled is False
    assert row.status == AttendanceStatus.PRESENT
    assert row.worked_minutes == 180
    assert calculate_attendance(acme, MONDAY + timedelta(days=1), MONDAY + timedelta(days=1)) == 0


def test_twenty_employees_over_thirty_days_match_the_manual_count(acme, acme_node):
    start = date(2026, 1, 5)
    days = [start + timedelta(days=offset) for offset in range(30)]
    holiday = date(2026, 1, 12)
    workdays = [day for day in days if day.isoweekday() <= 5 and day != holiday]
    department_a = Department.all_objects.create(organization=acme, name="Planta")
    department_b = Department.all_objects.create(organization=acme, name="Oficina")
    shift = _shift(acme, name="General", late=5, early=5)
    _department_schedule(acme, department_a, shift)
    _department_schedule(acme, department_b, shift)
    Holiday.all_objects.create(organization=acme, date=holiday, name="Festivo")
    employees = []
    logs = []
    for index in range(20):
        department = department_a if index < 10 else department_b
        employee = _employee(acme, f"E{index:02d}", department, f"Persona{index}")
        employees.append(employee)
        kind = index % 5
        for day in workdays:
            if kind == 0:
                continue
            if kind == 1:
                logs.append(_log(acme, acme_node, employee, _at(day, 8, 20), Direction.IN))
                logs.append(_log(acme, acme_node, employee, _at(day, 17, 0), Direction.OUT))
            elif kind == 2:
                logs.append(_log(acme, acme_node, employee, _at(day, 8, 0), Direction.IN))
                logs.append(_log(acme, acme_node, employee, _at(day, 16, 0), Direction.OUT))
            elif kind == 3:
                logs.append(_log(acme, acme_node, employee, _at(day, 8, 0), Direction.IN))
            else:
                logs.append(_log(acme, acme_node, employee, _at(day, 8, 0), Direction.IN))
                logs.append(_log(acme, acme_node, employee, _at(day, 17, 0), Direction.OUT))
    AccessLog.all_objects.bulk_create(logs, batch_size=500)

    end = days[-1]
    written = calculate_attendance(acme, start, end)
    per_pattern = 4 * len(workdays)
    assert written == per_pattern * 5 + 20

    counts = {
        status: DailyAttendance.all_objects.filter(status=status).count()
        for status in AttendanceStatus
    }
    assert counts[AttendanceStatus.ABSENT] == per_pattern
    assert counts[AttendanceStatus.LATE] == per_pattern
    assert counts[AttendanceStatus.EARLY_LEAVE] == per_pattern
    assert counts[AttendanceStatus.INCOMPLETE] == per_pattern
    assert counts[AttendanceStatus.PRESENT] == per_pattern
    assert counts[AttendanceStatus.HOLIDAY] == 20

    late = DailyAttendance.all_objects.get(employee=employees[1], work_date=workdays[0])
    assert late.late_minutes == 15
    assert late.early_leave_minutes == 0
    assert late.worked_minutes == 520

    early = DailyAttendance.all_objects.get(employee=employees[2], work_date=workdays[0])
    assert early.early_leave_minutes == 55
    assert early.worked_minutes == 480

    present = DailyAttendance.all_objects.get(employee=employees[4], work_date=workdays[0])
    assert present.worked_minutes == 540
    assert present.late_minutes == 0

    worked = DailyAttendance.all_objects.aggregate(total=Sum("worked_minutes"))["total"]
    assert worked == per_pattern * (520 + 480 + 540)

    again = calculate_attendance(acme, start, end)
    assert again == written
    assert DailyAttendance.all_objects.count() == written


def test_attendance_does_not_cross_organizations(acme, globex, acme_client, globex_client):
    organizations = ((acme, "ACME-1"), (globex, "GLX-1"))
    for organization, document in organizations:
        department = Department.all_objects.create(organization=organization, name="Nómina")
        shift = _shift(organization, name=f"Turno {organization.slug}")
        _department_schedule(organization, department, shift, weekdays=[1, 2, 3, 4, 5, 6, 7])
        _employee(organization, document, department)
        calculate_attendance(organization, MONDAY, MONDAY)

    acme_rows = acme_client.get("/api/v1/reports/attendance/")
    assert acme_rows.status_code == 200
    assert acme_rows.data["count"] == 1
    assert acme_rows.data["results"][0]["document_id"] == "ACME-1"
    foreign_id = DailyAttendance.all_objects.get(organization=globex).id
    assert acme_client.get(f"/api/v1/reports/attendance/{foreign_id}/").status_code == 404
    globex_rows = globex_client.get("/api/v1/reports/attendance/")
    assert [row["document_id"] for row in globex_rows.data["results"]] == ["GLX-1"]


def test_summary_rates_for_the_manual_day(acme, acme_node, operations, acme_client):
    shift = _shift(acme)
    _department_schedule(acme, operations, shift)
    ana = _employee(acme, "S-1", operations, "Ana")
    luis = _employee(acme, "S-2", operations, "Luis")
    _employee(acme, "S-3", operations, "Marta")
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, ana, _at(MONDAY, 8, 12), Direction.IN),
            _log(acme, acme_node, ana, _at(MONDAY, 16, 40), Direction.OUT),
            _log(acme, acme_node, luis, _at(MONDAY, 8, 0), Direction.IN),
        ]
    )
    response = acme_client.post(
        "/api/v1/reports/recalculate/",
        {"date_from": "2026-03-02", "date_to": "2026-03-02"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["rows"] == 3
    summary = acme_client.get(
        "/api/v1/reports/summary/",
        {"date_from": "2026-03-02", "date_to": "2026-03-02"},
    )
    assert summary.status_code == 200
    assert summary.data["expected_days"] == 3
    assert summary.data["present_days"] == 1
    assert summary.data["late_days"] == 1
    assert summary.data["early_leave_days"] == 1
    assert summary.data["absent_days"] == 1
    assert summary.data["incomplete_days"] == 1
    assert summary.data["worked_minutes"] == 508
    assert summary.data["punctuality_rate"] == 0.5
    assert summary.data["absenteeism_rate"] == 0.3333
    assert summary.data["by_department"][0]["name"] == "Operaciones"
    assert summary.data["by_day"][0]["date"] == "2026-03-02"
    filtered = acme_client.get(
        "/api/v1/reports/summary/",
        {"date_from": "2026-03-02", "date_to": "2026-03-02", "site": "Sede"},
    )
    assert filtered.data["absent_days"] == 0
    assert filtered.data["employees"] == 2


def test_schedule_rules_and_roles(
    acme, operations, acme_client, operator_client, viewer_client, globex
):
    shift = operator_client.post(
        "/api/v1/shifts/",
        {
            "name": "Diurna",
            "start_time": "08:00",
            "end_time": "17:00",
            "late_tolerance_minutes": 10,
            "early_leave_tolerance_minutes": 10,
            "is_active": True,
        },
        format="json",
    )
    assert shift.status_code == 201
    assert viewer_client.post("/api/v1/shifts/", {"name": "Otra"}, format="json").status_code == 403
    assert (
        operator_client.post(
            "/api/v1/shifts/",
            {"name": "Noche", "start_time": "22:00", "end_time": "06:00"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        operator_client.post(
            "/api/v1/shifts/",
            {"name": "Diurna", "start_time": "09:00", "end_time": "18:00"},
            format="json",
        ).status_code
        == 400
    )
    employee = _employee(acme, "R-1", operations)
    other = Employee.all_objects.create(
        organization=globex,
        document_id="G-1",
        first_name="Bruno",
        last_name="Díaz",
    )
    created = operator_client.post(
        "/api/v1/schedules/",
        {"shift": shift.data["id"], "department": str(operations.id), "weekdays": [1, 2, 3, 4, 5]},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["department_name"] == "Operaciones"
    assert (
        operator_client.post(
            "/api/v1/schedules/",
            {
                "shift": shift.data["id"],
                "employee": str(employee.id),
                "department": str(operations.id),
                "weekdays": [1],
            },
            format="json",
        ).status_code
        == 400
    )
    assert (
        operator_client.post(
            "/api/v1/schedules/",
            {"shift": shift.data["id"], "employee": str(other.id), "weekdays": [1]},
            format="json",
        ).status_code
        == 400
    )
    holiday = operator_client.post(
        "/api/v1/holidays/",
        {"date": "2026-12-25", "name": "Navidad"},
        format="json",
    )
    assert holiday.status_code == 201
    assert viewer_client.get("/api/v1/holidays/").status_code == 200
    assert viewer_client.delete(f"/api/v1/holidays/{holiday.data['id']}/").status_code == 403
    inverted = acme_client.post(
        "/api/v1/reports/recalculate/",
        {"date_from": "2026-03-10", "date_to": "2026-03-01"},
        format="json",
    )
    assert inverted.status_code == 400
    too_long = acme_client.post(
        "/api/v1/reports/recalculate/",
        {"date_from": "2024-01-01", "date_to": "2026-01-01"},
        format="json",
    )
    assert too_long.status_code == 400
    assert (
        viewer_client.post(
            "/api/v1/reports/recalculate/",
            {"date_from": "2026-03-02", "date_to": "2026-03-02"},
            format="json",
        ).status_code
        == 403
    )


def test_daily_task_rebuilds_local_yesterday_and_today(acme, acme_node, operations):
    shift = _shift(acme, name="Continua")
    _department_schedule(acme, operations, shift, weekdays=[1, 2, 3, 4, 5, 6, 7])
    ana = _employee(acme, "T-1", operations)
    local_today = timezone.now().astimezone(TZ).date()
    yesterday = local_today - timedelta(days=1)
    AccessLog.all_objects.bulk_create(
        [
            _log(acme, acme_node, ana, _at(yesterday, 8, 0), Direction.IN),
            _log(acme, acme_node, ana, _at(yesterday, 17, 0), Direction.OUT),
        ]
    )
    assert rebuild_daily_attendance() == 1
    row = DailyAttendance.all_objects.get(employee=ana, work_date=yesterday)
    assert row.status == AttendanceStatus.PRESENT
    assert row.worked_minutes == 540

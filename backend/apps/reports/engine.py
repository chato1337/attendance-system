"""Cálculo de asistencia diaria a partir de marcaciones concedidas.

Las reglas están descritas en docs/reports.md. Este módulo es la única
implementación: los reportes y las exportaciones leen DailyAttendance.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.access.models import AccessLog, AccessStatus, Direction
from apps.people.models import Employee
from apps.reports.models import (
    AttendanceStatus,
    DailyAttendance,
    Holiday,
    Schedule,
)

CLOSED = {
    AttendanceStatus.PRESENT,
    AttendanceStatus.LATE,
    AttendanceStatus.EARLY_LEAVE,
}


def calculate_attendance(organization, date_from, date_to, *, employee_ids=None) -> int:
    """Reescribe la asistencia de los empleados activos en el rango, inclusive."""
    if date_to < date_from:
        raise ValueError("La fecha final es anterior a la inicial.")

    tz = ZoneInfo(organization.timezone)
    employees = Employee.all_objects.filter(organization=organization, is_active=True)
    if employee_ids is not None:
        employees = employees.filter(id__in=employee_ids)
    employees = list(employees)
    if not employees:
        return 0

    ids = [employee.id for employee in employees]
    schedules = list(
        Schedule.all_objects.filter(organization=organization, is_active=True).select_related(
            "shift"
        )
    )
    by_employee, by_department = _index_schedules(schedules)
    holidays = set(
        Holiday.all_objects.filter(
            organization=organization,
            date__gte=date_from,
            date__lte=date_to,
        ).values_list("date", flat=True)
    )
    window_start = datetime.combine(date_from, time.min, tzinfo=tz)
    window_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    logs = (
        AccessLog.all_objects.filter(
            organization=organization,
            status=AccessStatus.GRANTED,
            employee_id__in=ids,
            timestamp__gte=window_start,
            timestamp__lt=window_end,
        )
        .select_related("node")
        .order_by("timestamp")
    )
    grouped: dict[tuple, list] = defaultdict(list)
    for log in logs:
        local_day = log.timestamp.astimezone(tz).date()
        if date_from <= local_day <= date_to:
            grouped[(log.employee_id, local_day)].append(log)

    calculated_at = timezone.now()
    computed: dict[tuple, dict] = {}
    day = date_from
    while day <= date_to:
        iso = day.isoweekday()
        holiday = day in holidays
        for employee in employees:
            shift = _shift_for(employee, iso, by_employee, by_department)
            payload = _day_row(
                employee,
                day,
                shift,
                holiday,
                grouped.get((employee.id, day), []),
                tz,
                calculated_at,
            )
            if payload is not None:
                computed[(employee.id, day)] = payload
        day += timedelta(days=1)

    return _persist(organization, ids, date_from, date_to, computed)


def _index_schedules(schedules):
    by_employee = defaultdict(list)
    by_department = defaultdict(list)
    for schedule in schedules:
        if not schedule.shift.is_active:
            continue
        if schedule.employee_id:
            by_employee[schedule.employee_id].append(schedule)
        elif schedule.department_id:
            by_department[schedule.department_id].append(schedule)
    return by_employee, by_department


def _shift_for(employee, iso, by_employee, by_department):
    personal = _pick(by_employee.get(employee.id, []), iso)
    if personal is not None:
        return personal
    if employee.department_id:
        return _pick(by_department.get(employee.department_id, []), iso)
    return None


def _pick(options, iso):
    matching = [item for item in options if iso in (item.weekdays or [])]
    if not matching:
        return None
    matching.sort(key=lambda item: item.updated_at, reverse=True)
    return matching[0].shift


def _day_row(employee, day, shift, holiday, logs, tz, calculated_at):
    first_in, last_out, worked, orphan, site, node_id = _stay(logs)
    scheduled = shift is not None
    if not scheduled and not logs:
        return None

    late = 0
    early = 0
    if shift is not None and logs and not holiday:
        if first_in is not None:
            late = _late_minutes(first_in, day, shift, tz)
        if last_out is not None:
            early = _early_minutes(last_out, day, shift, tz)

    status = _status(scheduled, holiday, logs, orphan, late, early)
    if status is None:
        return None
    return {
        "employee_id": employee.id,
        "department_id": employee.department_id,
        "node_id": node_id,
        "site": site,
        "work_date": day,
        "status": status,
        "is_holiday": holiday,
        "scheduled": scheduled,
        "shift_id": shift.id if shift else None,
        "expected_start": shift.start_time if shift else None,
        "expected_end": shift.end_time if shift else None,
        "first_in": first_in,
        "last_out": last_out,
        "worked_minutes": worked,
        "late_minutes": late,
        "early_leave_minutes": early,
        "orphan_in": orphan,
        "granted_count": len(logs),
        "calculated_at": calculated_at,
    }


def _status(scheduled, holiday, logs, orphan, late, early):
    if not logs:
        if holiday and scheduled:
            return AttendanceStatus.HOLIDAY
        if scheduled:
            return AttendanceStatus.ABSENT
        return None
    if orphan:
        return AttendanceStatus.INCOMPLETE
    if late > 0:
        return AttendanceStatus.LATE
    if early > 0:
        return AttendanceStatus.EARLY_LEAVE
    return AttendanceStatus.PRESENT


def _stay(logs):
    open_in = None
    first_in = None
    last_out = None
    worked_seconds = 0.0
    for log in logs:
        if log.direction == Direction.IN:
            if first_in is None:
                first_in = log.timestamp
            if open_in is None:
                open_in = log.timestamp
        elif log.direction == Direction.OUT and open_in is not None:
            worked_seconds += (log.timestamp - open_in).total_seconds()
            last_out = log.timestamp
            open_in = None
    site = ""
    node_id = None
    chosen = next((log for log in logs if log.direction == Direction.IN), None)
    if chosen is None and logs:
        chosen = logs[0]
    if chosen is not None:
        site = chosen.node.site or ""
        node_id = chosen.node_id
    return first_in, last_out, int(worked_seconds // 60), open_in is not None, site, node_id


def _late_minutes(moment, day, shift, tz) -> int:
    expected = datetime.combine(day, shift.start_time, tzinfo=tz)
    delta = int((moment.astimezone(tz) - expected).total_seconds() // 60)
    return max(0, delta - shift.late_tolerance_minutes)


def _early_minutes(moment, day, shift, tz) -> int:
    expected = datetime.combine(day, shift.end_time, tzinfo=tz)
    delta = int((expected - moment.astimezone(tz)).total_seconds() // 60)
    return max(0, delta - shift.early_leave_tolerance_minutes)


def _persist(organization, employee_ids, date_from, date_to, computed) -> int:
    existing = {
        (row.employee_id, row.work_date): row
        for row in DailyAttendance.all_objects.filter(
            organization=organization,
            employee_id__in=employee_ids,
            work_date__gte=date_from,
            work_date__lte=date_to,
        )
    }
    to_create = []
    to_update = []
    for key, payload in computed.items():
        current = existing.get(key)
        if current is None:
            to_create.append(DailyAttendance(organization=organization, **payload))
            continue
        for field, value in payload.items():
            setattr(current, field, value)
        to_update.append(current)
    stale = [row.pk for key, row in existing.items() if key not in computed]
    fields = [
        "department",
        "node",
        "site",
        "status",
        "is_holiday",
        "scheduled",
        "shift",
        "expected_start",
        "expected_end",
        "first_in",
        "last_out",
        "worked_minutes",
        "late_minutes",
        "early_leave_minutes",
        "orphan_in",
        "granted_count",
        "calculated_at",
    ]
    with transaction.atomic():
        if stale:
            DailyAttendance.all_objects.filter(pk__in=stale).delete()
        if to_create:
            DailyAttendance.all_objects.bulk_create(to_create, batch_size=500)
        if to_update:
            DailyAttendance.all_objects.bulk_update(to_update, fields, batch_size=500)
    return len(computed)


def attendance_queryset(organization, filters: dict):
    queryset = DailyAttendance.all_objects.filter(organization=organization)
    return apply_attendance_filters(queryset, filters)


def apply_attendance_filters(queryset, filters: dict):
    queryset = queryset.filter(
        work_date__gte=filters["date_from"],
        work_date__lte=filters["date_to"],
    )
    if filters.get("department"):
        queryset = queryset.filter(department_id=filters["department"])
    if filters.get("employee"):
        queryset = queryset.filter(employee_id=filters["employee"])
    if filters.get("site"):
        queryset = queryset.filter(site=filters["site"])
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    return queryset


def summarize(queryset, date_from, date_to) -> dict:
    from django.db.models import Count, Q, Sum

    totals = queryset.aggregate(
        worked_minutes=Sum("worked_minutes"),
        expected_days=Count("id", filter=Q(scheduled=True, is_holiday=False)),
        present_days=Count("id", filter=Q(status__in=CLOSED)),
        late_days=Count("id", filter=Q(late_minutes__gt=0)),
        early_leave_days=Count("id", filter=Q(early_leave_minutes__gt=0)),
        absent_days=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
        incomplete_days=Count("id", filter=Q(status=AttendanceStatus.INCOMPLETE)),
        holiday_days=Count("id", filter=Q(status=AttendanceStatus.HOLIDAY)),
        arrivals=Count("id", filter=Q(first_in__isnull=False, scheduled=True, is_holiday=False)),
        on_time=Count(
            "id",
            filter=Q(
                first_in__isnull=False,
                scheduled=True,
                is_holiday=False,
                late_minutes=0,
            ),
        ),
    )
    by_department = []
    grouped = (
        queryset.values("department_id", "department__name")
        .annotate(
            worked_minutes=Sum("worked_minutes"),
            late_days=Count("id", filter=Q(late_minutes__gt=0)),
            absent_days=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
            employees=Count("employee_id", distinct=True),
        )
        .order_by("department__name")
    )
    for row in grouped:
        by_department.append(
            {
                "department_id": row["department_id"],
                "name": row["department__name"] or "Sin departamento",
                "worked_minutes": row["worked_minutes"] or 0,
                "late_days": row["late_days"],
                "absent_days": row["absent_days"],
                "employees": row["employees"],
            }
        )
    by_day_rows = {
        row["work_date"]: row
        for row in queryset.values("work_date").annotate(
            present=Count("id", filter=Q(status__in=CLOSED)),
            absent=Count("id", filter=Q(status=AttendanceStatus.ABSENT)),
            late=Count("id", filter=Q(late_minutes__gt=0)),
            worked_minutes=Sum("worked_minutes"),
        )
    }
    by_day = []
    cursor = date_from
    while cursor <= date_to:
        row = by_day_rows.get(cursor)
        by_day.append(
            {
                "date": cursor.isoformat(),
                "present": row["present"] if row else 0,
                "absent": row["absent"] if row else 0,
                "late": row["late"] if row else 0,
                "worked_minutes": (row["worked_minutes"] or 0) if row else 0,
            }
        )
        cursor += timedelta(days=1)
    expected = totals["expected_days"] or 0
    arrivals = totals["arrivals"] or 0
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "employees": queryset.values("employee_id").distinct().count(),
        "expected_days": expected,
        "present_days": totals["present_days"] or 0,
        "late_days": totals["late_days"] or 0,
        "early_leave_days": totals["early_leave_days"] or 0,
        "absent_days": totals["absent_days"] or 0,
        "incomplete_days": totals["incomplete_days"] or 0,
        "holiday_days": totals["holiday_days"] or 0,
        "worked_minutes": totals["worked_minutes"] or 0,
        "punctuality_rate": _rate(totals["on_time"] or 0, arrivals),
        "absenteeism_rate": _rate(totals["absent_days"] or 0, expected),
        "by_department": by_department,
        "by_day": by_day,
    }


def _rate(numerator: int, denominator: int):
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)

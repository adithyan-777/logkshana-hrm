from django.db.models import Q, QuerySet

from attendance.models import Attendance, AttendanceActivity, WorkSession
from common.localtime import local_date
from employees.models import Employee


def attendance_activity_list(
    *, search: str = "", employee: Employee | None = None
) -> QuerySet[AttendanceActivity]:
    queryset = AttendanceActivity.objects.select_related("employee").order_by(
        "-punch_time"
    )

    if employee is not None:
        queryset = queryset.filter(employee=employee)

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(external_id__icontains=search)
        )

    return queryset


def attendance_list(
    *, search: str = "", employee: Employee | None = None
) -> QuerySet[Attendance]:
    queryset = Attendance.objects.select_related(
        "employee", "shift"
    ).order_by("-day")

    if employee is not None:
        queryset = queryset.filter(employee=employee)

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
            | Q(status__icontains=search)
        )

    return queryset


def work_session_list(*, search: str = "") -> QuerySet[WorkSession]:
    queryset = WorkSession.objects.select_related(
        "employee", "in_punch", "out_punch"
    ).order_by("-day", "-check_in")

    if search:
        queryset = queryset.filter(
            Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(employee__emp_code__icontains=search)
        )

    return queryset


def attendance_exception_day_list(
    *,
    search: str = "",
    status: str = "",
    date_from=None,
    date_to=None,
) -> list[dict]:
    """The punch-flow exception queue, grouped per (employee, day).

    One exception = one employee-day whose punch flow has problems:
    - ``missing_checkout``: a WorkSession still open on a PAST day
      (today's open sessions are work-in-progress, not exceptions —
      they only count from the next day, mirroring the pairing
      engine's opening-time day boundary),
    - ``stray_checkout``: ignored check-outs (logged, nothing to close),
    - ``duplicate_punch``: ignored duplicate check-ins (informational
      — pairing absorbs them by design, but they expose device
      misreads worth correcting).

    A day whose only entry is a correction is ``resolved`` (the
    correction history travels with the row); a day with corrections
    AND live problems shows both. Returned ordered: problem days
    first, then most recent.
    """
    today = local_date()

    # Correction rows never count as exceptions: they are the
    # resolution path. A correction that cannot pair during the replay
    # (a forgotten-checkout day flipped in -> out) is flagged ignored
    # by the engine, but that flag describes the intended state, not
    # a problem to resolve.
    not_correction = ~Q(
        method=AttendanceActivity.AttendanceActivityMethodType.CORRECTION
    )

    def _day_range(qs, field):
        if date_from is not None:
            qs = qs.filter(**{f"{field}__gte": date_from})
        if date_to is not None:
            qs = qs.filter(**{f"{field}__lte": date_to})
        return qs

    def _search(qs):
        if search:
            return qs.filter(
                Q(employee__first_name__icontains=search)
                | Q(employee__last_name__icontains=search)
                | Q(employee__emp_code__icontains=search)
            )
        return qs

    days: dict[tuple, dict] = {}

    def _entry(employee, day):
        key = (employee.pk, day)
        if key not in days:
            days[key] = {
                "employee": employee,
                "day": day,
                "open_sessions": [],
                "stray_outs": [],
                "duplicate_ins": [],
                "corrected": [],
            }
        return days[key]

    for session in (
        _search(_day_range(WorkSession.objects, "day"))
        .filter(check_out__isnull=True)
        .exclude(day=today)
        .select_related("employee")
        .order_by("day")
    ):
        _entry(session.employee, session.day)["open_sessions"].append(session)

    ignored_punches = (
        _search(_day_range(AttendanceActivity.objects, "punch_time__date"))
        .filter(
            not_correction,
            ignored=True,
            direction__in=[
                AttendanceActivity.Direction.IN,
                AttendanceActivity.Direction.OUT,
            ],
        )
        .select_related("employee", "corrected_punch")
        .order_by("punch_time")
    )
    for punch in ignored_punches:
        # Wall-clock day grouping must match the pairing engine's
        # session-day attribution (the day the punch was entered with).
        entry = _entry(punch.employee, local_date(punch.punch_time))
        if punch.direction == AttendanceActivity.Direction.OUT:
            entry["stray_outs"].append(punch)
        else:
            entry["duplicate_ins"].append(punch)

    corrected_punches = (
        _search(_day_range(AttendanceActivity.objects, "punch_time__date"))
        .filter(corrected_punch__isnull=False)
        .select_related("employee", "corrected_punch", "corrected_punch__edited_by")
        .order_by("punch_time")
    )
    for punch in corrected_punches:
        entry = _entry(punch.employee, local_date(punch.punch_time))
        entry["corrected"].append(punch)

    for entry in days.values():
        entry["has_problems"] = bool(entry["open_sessions"] or entry["stray_outs"])
        entry["resolved"] = bool(entry["corrected"]) and not entry["has_problems"]

    entries = list(days.values())
    if status == "unresolved":
        entries = [e for e in entries if e["has_problems"]]
    elif status == "resolved":
        entries = [e for e in entries if e["resolved"]]
    entries.sort(key=lambda e: (not e["has_problems"], -e["day"].toordinal()))
    return entries

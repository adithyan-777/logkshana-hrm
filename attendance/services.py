from datetime import date, datetime, time, timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Min, OuterRef, Q, Subquery, Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.calculation import direction_from_gateway_status_label
from attendance.integrations.gateway import device_gateway_attendance_fetch
from attendance.models import (
    Attendance,
    AttendanceActivity,
    WorkSession,
)
from companies.selectors import device_get_by_serial_number
from employees.models import Employee
from employees.selectors import employee_get_by_emp_code
from employees.services import employee_create
from policies.selectors import (
    attendance_policy_is_unscheduled,
    unscheduled_opening_time_get,
)


@transaction.atomic
def activity_create(
    *,
    employee,
    punch_time,
    direction: str = AttendanceActivity.Direction.UNKNOWN,
    method: str = AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
    external_id: str | None = None,
    raw_data=None,
) -> AttendanceActivity:
    if not external_id:
        external_id = f"manual:{uuid4().hex}"
    else:
        existing = AttendanceActivity.objects.filter(external_id=external_id).first()
        if existing is not None:
            return existing
    activity = AttendanceActivity(
        employee=employee,
        punch_time=punch_time,
        direction=direction,
        method=method,
        external_id=external_id,
        raw_data=raw_data or {},
    )
    activity.full_clean()
    activity.save()
    # Punch-based Attendance calculation only runs when the tenant
    # policy is "unscheduled". In "scheduled" mode the punch is just
    # recorded; Attendance rows come from the (schedule-driven)
    # calculation instead.
    if attendance_policy_is_unscheduled():
        attendance_update_for_punch(
            employee=activity.employee,
            punch_time=activity.punch_time,
            direction=activity.direction,
            activity=activity,
        )
    return activity


@transaction.atomic
def activity_update(
    *,
    activity: AttendanceActivity,
    employee,
    punch_time,
    direction: str,
    method: str,
    external_id: str | None = None,
    raw_data=None,
) -> AttendanceActivity:
    activity.employee = employee
    # external_id is a stable record identifier: keep the existing one
    # unless an explicit replacement is given.
    if external_id:
        activity.external_id = external_id
    activity.punch_time = punch_time
    activity.direction = direction
    activity.method = method
    activity.raw_data = raw_data or {}
    activity.full_clean()
    activity.save()
    return activity


@transaction.atomic
def activity_delete(*, activity: AttendanceActivity) -> AttendanceActivity:
    """Deletes the punch."""
    activity.delete()
    return activity


@transaction.atomic
def attendance_record_create(
    *,
    employee,
    day,
    status: str,
    shift=None,
) -> Attendance:
    """Create a hand-made attendance row (never auto-overwritten)."""
    row = Attendance(
        employee=employee,
        day=day,
        status=status,
        shift=shift,
        is_calculated=False,
    )
    row.full_clean()
    row.save()
    return row


@transaction.atomic
def attendance_record_update(
    *,
    attendance: Attendance,
    employee,
    day,
    status: str,
    shift=None,
) -> Attendance:
    attendance.employee = employee
    attendance.day = day
    attendance.status = status
    attendance.shift = shift
    attendance.is_calculated = False
    attendance.full_clean()
    attendance.save()
    return attendance


@transaction.atomic
def attendance_record_delete(*, attendance: Attendance) -> Attendance:
    """Deletes a hand-made attendance record.

    Calculated rows are written by the daily calculation: they are
    removed by dropping the punches, never by hand.
    """
    if attendance.is_calculated:
        raise ValidationError(
            "Calculated attendance cannot be deleted; remove the punch or "
            "the schedule entry instead."
        )
    attendance.delete()
    return attendance


# -- Auto-ABSENT midnight job -------------------------------------------


def employees_absent_condition(*, day: date):
    """Employees eligible for an auto-ABSENT row on ``day``.

    Single pluggable rule for the midnight job. An employee is
    eligible when they are active, hold no Attendance row for the
    day, have no punches already recorded that day, and were punched
    OUT before the day started (their last punch is a check-out — or
    they never punched at all).

    An employee whose last punch is a check-in might still be in the
    building (overnight shift, missed check-out), so they are skipped.
    Tweak the query here to change who gets marked absent (branch,
    employee_type, schedule coverage, ...).
    """
    day_start = timezone.make_aware(datetime.combine(day, time.min))
    last_direction = AttendanceActivity.objects.filter(
        employee=OuterRef("pk"),
        punch_time__lt=day_start,
    ).order_by("-punch_time", "-id").values("direction")[:1]
    return (
        Employee.objects.filter(is_active=True)
        .exclude(
            attendances__day=day,
        )
        .exclude(
            attendance_activities__punch_time__gte=day_start,
            attendance_activities__punch_time__lt=day_start + timedelta(days=1),
        )
        .annotate(last_direction=Subquery(last_direction))
        .filter(
            Q(last_direction=AttendanceActivity.Direction.OUT)
            | Q(last_direction__isnull=True)
        )
    )


@transaction.atomic
def attendance_absent_rows_ensure(*, day: date) -> list[Attendance]:
    """Create auto-ABSENT Attendance rows for every eligible employee.

    Idempotent: employees already holding a row for ``day`` are
    excluded by the condition, and ``get_or_create`` absorbs races.
    Rows are written with ``is_calculated=False`` (machine-generated
    today, but treated like hand-made rows — the future daily
    calculation never overwrites them).
    """
    created = []
    for employee in employees_absent_condition(day=day).iterator():
        row, was_created = Attendance.objects.get_or_create(
            employee=employee,
            day=day,
            defaults={
                "status": Attendance.Status.ABSENT,
                "is_calculated": False,
            },
        )
        if was_created:
            created.append(row)
    return created
# -- Punch -> WorkSession pairing ----------------------------------------


def _attendance_row_ensure(*, employee, day) -> Attendance:
    row, _ = Attendance.objects.get_or_create(
        employee=employee,
        day=day,
        defaults={
            "status": Attendance.Status.ABSENT,
            "is_calculated": False,
        },
    )
    return row


def _open_work_session_get(*, employee) -> WorkSession | None:
    """The employee's most recent open (unclosed) work session.

    Only one open session can exist at a time; ordering covers the
    overnight case, where the open session belongs to an earlier day.
    """
    return (
        WorkSession.objects.filter(
            employee=employee,
            check_out__isnull=True,
        )
        .order_by("-day", "-check_in")
        .first()
    )


def _activity_attendance_link(activity, attendance):
    """Link a consumed punch to the day row it was processed into.

    Powers the punch-log view (``is_attendance_processed``); punch
    rows ingested without an activity (direct primitive calls, tests)
    skip the link.
    """
    if activity is not None and activity.attendance_id is None:
        activity.attendance = attendance
        activity.save(update_fields=["attendance", "updated_at"])


# The next-day-OUT day boundary is per tenant: the configured
# UnscheduledConfig.opening_time. A next-day OUT closes yesterday's
# open session only earlier than that opening — past it the punch is
# the new day's stray check-out and yesterday's session stays open
# (forgotten punch-out). No configured opening means no day boundary:
# unbounded behavior (any next-day OUT closes yesterday's session).


def _previous_day_out_is_stale(
    *,
    open_session_day,
    punch_day,
    punch_local_time,
) -> bool:
    """True when an OUT on a new day must not close yesterday's session.

    A next-day OUT closes the previous day's open session only earlier
    than the tenant's configured opening time — a genuine overnight
    shift wraps up before the workplace opens for the new day. From the
    configured opening onward the punch is someone's stray check-out on
    the new day (the forgotten-punch-out story), and yesterday's
    session stays open. Missing config or a null opening_time means no
    day boundary: nothing is ever stale on day grounds.
    """
    if open_session_day == punch_day:
        return False
    opening_time = unscheduled_opening_time_get()
    return opening_time is not None and punch_local_time > opening_time


@transaction.atomic
def attendance_update_for_punch(
    *,
    employee,
    punch_time,
    direction: str,
    activity: AttendanceActivity | None = None,
) -> Attendance | None:
    """Apply one punch to the employee's attendance via work sessions.

    An IN punch opens a new ``WorkSession`` under the punch day's daily
    row (created on demand) — even while another session is still open
    (double punch, missed punch-out): the earlier session keeps its
    punches and stays open until a later OUT closes it. The daily
    ``check_in`` stamps only the day's first session.

    An OUT punch closes the most recent open session — today first,
    then an earlier day's (overnight shift) — records ``total_time``
    on the session, moves the daily ``check_out`` to that session's
    out time, and refreshes ``total_work_time`` as the sum of the
    closed sessions. A next-day OUT closes a previous day's session
    only earlier than the tenant's configured opening time
    (UnscheduledConfig.opening_time); with no configured opening the
    boundary is unbounded. Past the configured opening it stays
    punch-log-only and yesterday's session remains open.
    An OUT with no open session and an OUT earlier than the open
    session's ``check_in`` stay punch-log-only and touch no rows.

    Replay-safe: an IN that already owns a session and an OUT that
    already closed one are idempotent no-ops (returning the row they
    were originally processed into), so re-processing a punch stream
    (recalculation scripts, gateway replays) is safe.

    Punches with an unknown direction (devices sending no status
    label) leave rows untouched.
    """
    # Punch times come in as local wall-clock — use them as-is, no
    # localization pass on the way in.
    punch_day = punch_time.date()
    punch_local_time = punch_time.time()
    if direction == AttendanceActivity.Direction.IN:
        # Replay/idempotency: an IN that already opened a session (now
        # possibly closed) owns exactly one session forever — do not
        # create a dupe (``uniq_worksession_in_punch``) and do not
        # re-link it elsewhere.
        if activity is not None:
            owned = WorkSession.objects.filter(in_punch=activity).first()
            if owned is not None:
                return owned.attendance
        # Every IN opens its own session — including a same-day double
        # punch: the earlier open session keeps its punches and waits
        # for a later OUT (a missed punch-out is never silently
        # rewritten into a double-punch absorb).
        row = _attendance_row_ensure(employee=employee, day=punch_day)
        WorkSession.objects.create(
            employee=employee,
            attendance=row,
            day=punch_day,
            in_punch=activity,
            check_in=punch_time,
        )
        if row.check_in is None:
            row.check_in = punch_time
            if row.status in (
                Attendance.Status.ABSENT,
                Attendance.Status.INCOMPLETE,
            ):
                row.status = Attendance.Status.PRESENT
        row.save(update_fields=["check_in", "status", "updated_at"])
        _activity_attendance_link(activity, row)
        return row
    if direction == AttendanceActivity.Direction.OUT:
        # Replay/idempotency: an OUT that already closed its session
        # must not close a second one on the next pass.
        if activity is not None:
            consumed = WorkSession.objects.filter(out_punch=activity).first()
            if consumed is not None:
                return consumed.attendance
        session = _open_work_session_get(employee=employee)
        if session is None:
            # Stray OUT: record it in the punch log only; daily rows
            # are not created or stamped for unpaired check-outs.
            return None
        if _previous_day_out_is_stale(
            open_session_day=session.day,
            punch_day=punch_day,
            punch_local_time=punch_local_time,
        ):
            # Past the tenant's configured opening: yesterday's session
            # was never closed (forgotten punch-out) and this OUT
            # belongs to the new day — punch-log-only, the session
            # stays open.
            return None
        if punch_time <= session.check_in:
            # Stale or replayed punch — never pair backwards in time.
            return None
        session.out_punch = activity
        session.check_out = punch_time
        session.total_time = punch_time - session.check_in
        session.save(
            update_fields=["out_punch", "check_out", "total_time", "updated_at"]
        )
        row = session.attendance
        row.check_out = session.check_out
        row.total_work_time = (
            WorkSession.objects.filter(
                attendance=row,
                check_out__isnull=False,
            )
            .aggregate(total=Sum("total_time"))["total"]
            or timedelta(0)
        )
        row.save(update_fields=["check_out", "total_work_time", "updated_at"])
        _activity_attendance_link(activity, row)
        return row
    return None


# -- Manual punches & corrections: re-coupling ---------------------------
#
# The pairing primitive only ever pairs forward: an IN opens its own
# session, an OUT closes the most recent open one — it can never
# un-pair. A punch added through ``activity_create`` is fine this way
# (it pairs on entry), but an EDIT or DELETE of a punch leaves the
# derived state stale: the session keeps the old check-in/total and the
# daily row keeps the old boundaries. The service below re-runs the
# derivation around one changed punch so the punch log stays the
# single source of truth.


def _punch_scope_days(
    *,
    activity: AttendanceActivity,
    previous_employee: Employee | None = None,
    previous_punch_time: datetime | None = None,
) -> dict[int, set[date]]:
    """Employee pk -> days whose derivation can mention this punch.

    The punch's own day anchors the window (± 1 day is applied later).
    An edited punch can also move between days or employees, and its
    session may wrap past midnight (an 23:00 IN accrues to its own day
    while the OUT falls on the next calendar day), so the days of the
    sessions it opens or closes — and of the partner punches that
    opened them — are anchored as well.
    """
    scope: dict[int, set[date]] = {}

    def _anchor(employee_id, punch_time):
        if employee_id is not None and punch_time is not None:
            scope.setdefault(employee_id, set()).add(punch_time.date())

    _anchor(activity.employee_id, activity.punch_time)
    _anchor(
        previous_employee.pk if previous_employee else None,
        previous_punch_time,
    )
    owned = WorkSession.objects.filter(
        Q(in_punch=activity) | Q(out_punch=activity)
    ).select_related("in_punch", "out_punch")
    for session in owned:
        partner_in = session.in_punch.punch_time if session.in_punch else None
        _anchor(session.employee_id, partner_in)
        if session.out_punch is not None and session.out_punch_id != activity.pk:
            _anchor(session.out_punch.employee_id, session.out_punch.punch_time)
    return scope


def _attendance_row_refresh(*, row: Attendance, had_sessions: bool) -> None:
    """Recompute one daily row from its (rebuilt) work sessions.

    Mirrors what the pairing primitive writes on the OUT path: the row
    boundaries come from the earliest session's check-in, the latest
    closed session's check-out, and the sum of closed session
    durations. Status is left to the pairing (an IN flips ABSENT/
    INCOMPLETE to PRESENT, hand-made statuses are kept) — except that
    a row which lost every session it used to have (e.g. its punch was
    deleted) is demoted from PRESENT to INCOMPLETE.
    """
    stats = WorkSession.objects.filter(attendance=row).aggregate(
        first_in=Min("check_in"),
        last_out=Max("check_out"),
        total=Sum("total_time", filter=Q(check_out__isnull=False)),
        session_count=Count("pk"),
    )
    row.check_in = stats["first_in"]
    row.check_out = stats["last_out"]
    row.total_work_time = stats["total"] or timedelta(0)
    if (
        stats["session_count"] == 0
        and had_sessions
        and row.status == Attendance.Status.PRESENT
    ):
        row.status = Attendance.Status.INCOMPLETE
    row.save(
        update_fields=[
            "check_in", "check_out", "total_work_time", "status", "updated_at",
        ]
    )


def _punch_links_repair(*, punches: list[AttendanceActivity]) -> None:
    """Re-point window punches to the rows their sessions landed on.

    The reset clears every window punch's attendance link, and
    ``_activity_attendance_link`` only fills a NULL — so a punch whose
    pairing is the idempotent early-return (an OUT that re-closes a
    session kept from before the window) would stay unlinked forever.
    Derive the link back from the punch's session (unconditionally:
    the reset cleared the links, so the write is always a repair).
    """
    for punch in punches:
        if punch.direction == AttendanceActivity.Direction.IN:
            session = WorkSession.objects.filter(
                in_punch=punch
            ).only("attendance_id").first()
        elif punch.direction == AttendanceActivity.Direction.OUT:
            session = WorkSession.objects.filter(
                out_punch=punch
            ).only("attendance_id").first()
        else:
            continue
        if session is not None:
            AttendanceActivity.objects.filter(pk=punch.pk).update(
                attendance_id=session.attendance_id
            )


def _punch_window_replay(
    *,
    employee: Employee,
    window_start: date,
    window_end: date,
    skip_activity: AttendanceActivity | None = None,
) -> list[Attendance]:
    """Reset and replay one employee's derived state for a day window.

    Sessions and daily-row stamps inside the window are wiped (status
    is kept, as in the replay script's reset) and rebuilt by replaying
    the window's punches chronologically through the pairing primitive
    — so every production rule (the opening-time day boundary, the
    no-backwards guard, overnight closes) applies as if the punches
    had just arrived. Sessions from before the window are kept: a
    window OUT that originally closed one re-pairs by idempotency.
    """
    had_sessions = set(
        Attendance.objects.filter(
            employee=employee,
            day__gte=window_start,
            day__lte=window_end,
            work_sessions__isnull=False,
        ).values_list("pk", flat=True)
    )
    WorkSession.objects.filter(
        employee=employee,
        day__gte=window_start,
        day__lte=window_end,
    ).delete()
    punches = [
        punch
        for punch in AttendanceActivity.objects.filter(
            employee=employee,
            punch_time__date__gte=window_start,
            punch_time__date__lte=window_end,
        )
        .order_by("punch_time", "id")
        if punch.pk != (skip_activity.pk if skip_activity else None)
    ]
    AttendanceActivity.objects.filter(
        pk__in=[punch.pk for punch in punches]
    ).update(attendance=None)
    Attendance.objects.filter(
        employee=employee,
        day__gte=window_start,
        day__lte=window_end,
    ).update(
        check_in=None, check_out=None, total_work_time=timedelta(0)
    )
    for punch in punches:
        attendance_update_for_punch(
            employee=employee,
            punch_time=punch.punch_time,
            direction=punch.direction,
            activity=punch,
        )
    rows = list(
        Attendance.objects.filter(
            employee=employee,
            day__gte=window_start,
            day__lte=window_end,
        ).order_by("day")
    )
    for row in rows:
        _attendance_row_refresh(
            row=row, had_sessions=row.pk in had_sessions
        )
    _punch_links_repair(punches=punches)
    return rows


@transaction.atomic
def punch_apply(
    *,
    activity: AttendanceActivity,
    previous_employee: Employee | None = None,
    previous_punch_time: datetime | None = None,
    deleted: bool = False,
) -> list[Attendance]:
    """Re-couple one manual punch or correction to its derived state.

    Called after a punch is added, edited (time/direction/employee) or
    about to be deleted, so its WorkSessions and daily Attendance rows
    follow the punch log again.

    Phase 1 — scope: the punch's day (plus its previous day/time when
    it was edited, and the days of the sessions it opens or closes)
    fixes the window; sessions closed by a much later punch-out (the
    unbounded no-opening-time boundary) pull the window's end forward
    so the replay re-pairs those closes too.
    Phase 2 — replay: each affected employee's window is reset and
    re-derived through the pairing primitive (``_punch_window_replay``).
    Phase 3 — refresh: daily rows are recomputed from their rebuilt
    sessions (``_attendance_row_refresh``).

    Manual daily corrections (``daily_add`` rows) are touched only
    where the derivation actually reaches them: their status is kept,
    their times are recomputed from sessions — which hand-made rows
    normally do not have.
    """
    if not attendance_policy_is_unscheduled():
        # Punch derivation only exists for the unscheduled policy —
        # keep in sync with activity_create (scheduled mode just
        # records the punch).
        return []
    scope = _punch_scope_days(
        activity=activity,
        previous_employee=previous_employee,
        previous_punch_time=previous_punch_time,
    )
    # Replay order matters when a punch was moved between employees:
    # the previous employee's window must be rebuilt first so the
    # punch's old session (still FK'd to that employee) is gone before
    # the current employee's replay re-pairs the punch — otherwise the
    # IN idempotency check finds the stale session and no-ops.
    order: list[int] = []

    def _queue(employee_id):
        if employee_id in scope and employee_id not in order:
            order.append(employee_id)

    _queue(previous_employee.pk if previous_employee else None)
    for session in WorkSession.objects.filter(
        Q(in_punch=activity) | Q(out_punch=activity)
    ):
        _queue(session.employee_id)
    _queue(activity.employee_id)
    for employee_id in scope:
        _queue(employee_id)

    refreshed: list[Attendance] = []
    for employee_id in order:
        punch_days = scope[employee_id]
        window_start = min(punch_days) - timedelta(days=1)
        window_end = max(punch_days) + timedelta(days=1)
        # A session built from window punches may be closed by a punch
        # far outside the window (no opening time configured means any
        # next-day OUT closes yesterday's session). Pull its day in, or
        # the replay would rebuild that session open.
        latest_out = (
            WorkSession.objects.filter(
                employee_id=employee_id,
                day__gte=window_start,
                out_punch__isnull=False,
            )
            .aggregate(latest=Max("out_punch__punch_time"))["latest"]
        )
        if latest_out is not None and latest_out.date() > window_end:
            window_end = latest_out.date()
        employee = Employee.objects.get(pk=employee_id)
        refreshed += _punch_window_replay(
            employee=employee,
            window_start=window_start,
            window_end=window_end,
            skip_activity=activity if deleted else None,
        )
    if deleted:
        activity.delete()
    return refreshed


@transaction.atomic
def punch_edit(
    *,
    activity: AttendanceActivity,
    employee,
    punch_time,
    direction: str,
    method: str,
    external_id: str | None = None,
    raw_data=None,
) -> list[Attendance]:
    """Update a punch and re-couple its derived state.

    Wraps ``activity_update`` + ``punch_apply``: the previous
    employee/punch time are captured so a moved punch (different day or
    a different employee) repairs the old day's rows too.
    """
    previous_employee = activity.employee
    previous_punch_time = activity.punch_time
    activity_update(
        activity=activity,
        employee=employee,
        punch_time=punch_time,
        direction=direction,
        method=method,
        external_id=external_id,
        raw_data=raw_data,
    )
    return punch_apply(
        activity=activity,
        previous_employee=previous_employee,
        previous_punch_time=previous_punch_time,
    )


@transaction.atomic
def punch_delete(*, activity: AttendanceActivity) -> list[Attendance]:
    """Delete a punch and rebuild the rows it used to feed.

    The punch itself is removed whatever the policy mode; only the
    work-session/attendance re-derivation is unscheduled-only.
    """
    if not attendance_policy_is_unscheduled():
        activity.delete()
        return []
    return punch_apply(activity=activity, deleted=True)


def _employee_get_or_create_for_device(*, emp_code: str, branch=None) -> Employee:
    employee = employee_get_by_emp_code(emp_code=emp_code)
    if employee is not None:
        return employee

    return employee_create(
        first_name="Device",
        last_name=emp_code,
        emp_code=emp_code,
        branch=branch,
        # Punch-only record: no phone/password known; employee_create
        # generates a random password (invite link can set a known one).
        sync_to_device=False,
    )


def device_attendance_pull(
    *,
    serial_number: str,
    after_id: int | None = None,
    auto_create_employee: bool = True,
) -> dict:
    from companies.services import device_sync_state_update

    # Device is a SHARED_APPS model (lives in public schema). Always fetch it
    # in the public schema so the task works regardless of which schema the
    # worker connection is currently set to.
    with schema_context(get_public_schema_name()):
        device = device_get_by_serial_number(serial_number=serial_number)
        if device is None:
            raise ValidationError({"serial_number": "Unknown device serial number."})
        if not device.is_active:
            raise ValidationError({"serial_number": "Device is inactive."})
        tenant_schema = device.company.schema_name
        if tenant_schema == get_public_schema_name():
            raise ValidationError(
                {
                    "serial_number": "Device is assigned to the public schema; reassign it to a real company/tenant."
                }
            )
        # Capture branch/id while still in public schema; Branch is shared.
        device_branch_id = device.branch_id
        if after_id is None and device.last_gateway_log_id:
            after_id = device.last_gateway_log_id
        last_gateway_log_id = device.last_gateway_log_id

    try:
        logs = device_gateway_attendance_fetch(
            serial_number=serial_number,
            after_id=after_id,
        )
    except ValidationError as exc:
        with schema_context(get_public_schema_name()):
            device_sync_state_update(device=device, error=str(exc.message_dict))
        raise
    except Exception as exc:
        # Transient gateway errors (HTTPError 5xx, URLError, TimeoutError,
        # OSError) are raised directly by the gateway to allow task-layer retry.
        from urllib.error import HTTPError, URLError

        if isinstance(exc, (HTTPError, URLError, TimeoutError, OSError)):
            with schema_context(get_public_schema_name()):
                device_sync_state_update(
                    device=device, error=f"{type(exc).__name__}: {exc}"
                )
            raise
        raise

    created = 0
    skipped = 0
    max_log_id = last_gateway_log_id

    with schema_context(tenant_schema):
        for log in logs:
            # Gateway identifies logs with ``gateway_log_id`` (older
            # payloads used ``id``); accept either.
            log_id = log.get("id")
            if log_id is None:
                log_id = log.get("gateway_log_id")
            if log_id is None:
                skipped += 1
                continue
            # Gateway payloads may stringify the id; the cursor handed back
            # to the next fetch is an integer.
            try:
                log_id = int(log_id)
            except (TypeError, ValueError):
                skipped += 1
                continue

            max_log_id = max(max_log_id, log_id)
            # Gateway sends ``user_id`` (device PIN); tolerate ``employee_id``.
            emp_code = log.get("user_id", log.get("employee_id"))
            if emp_code is None:
                skipped += 1
                continue
            emp_code = str(emp_code)
            timestamp_raw = log.get("timestamp")
            timestamp = parse_datetime(timestamp_raw) if timestamp_raw else None
            if timestamp is None:
                skipped += 1
                continue

            external_id = f"gateway:{log_id}"
            if AttendanceActivity.objects.filter(external_id=external_id).exists():
                skipped += 1
                continue

            try:
                employee = employee_get_by_emp_code(emp_code=emp_code)
            except ValidationError:
                skipped += 1
                continue

            if employee is None:
                # ``employee_get_by_emp_code`` only sees active records, so an
                # existing-but-deactivated code would otherwise be treated as
                # unknown and auto-created a second time.
                if Employee.objects.filter(emp_code=emp_code).exists():
                    skipped += 1
                    continue
                if not auto_create_employee:
                    skipped += 1
                    continue
                # Branch is a SHARED model (in public). Resolve it by id inside
                # the tenant context so the FK save works and we don't pass a
                # stale instance across schema_context boundaries.
                branch = None
                if device_branch_id is not None:
                    from companies.models import Branch

                    # Branch lives in public (shared), visible from tenant via search_path
                    branch = Branch.objects.filter(pk=device_branch_id).first()
                employee = _employee_get_or_create_for_device(
                    emp_code=emp_code,
                    branch=branch,
                )

            activity_create(
                employee=employee,
                punch_time=timestamp,
                direction=direction_from_gateway_status_label(log.get("status_label")),
                method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
                external_id=external_id,
                raw_data=log,
            )
            created += 1

    # Device state lives in public schema, so switch back before saving.
    with schema_context(get_public_schema_name()):
        device_sync_state_update(
            device=device,
            last_gateway_log_id=max_log_id,
            error="",
        )

    return {
        "serial_number": serial_number,
        "created": created,
        "skipped": skipped,
        "last_log_id": max_log_id,
    }

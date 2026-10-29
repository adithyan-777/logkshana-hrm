"""Rebuild WorkSessions + daily Attendance rows from the punch log.

Replays AttendanceActivity punches (chronologically, per employee)
through ``attendance_update_for_punch`` — the project's own pairing
primitive — so the re-derivation uses production rules: every IN opens
its own WorkSession (double punches and next-day INs included), an OUT
closes the latest open session, a next-day OUT closes yesterday's
session only earlier than the tenant's configured opening time
(UnscheduledConfig.opening_time; with no configured opening the
boundary is unbounded — past the opening — and in the absence of any
OUT — the session stays open).

The run is idempotent: already-paired days absorb their INs (no new
sessions), backward/same-moment OUTs are rejected by the stale punch
guard, and the ``uniq_worksession_in_punch`` constraint makes any
dupe attempt fail loudly. Derived state only — hand-made rows and
corrections (``is_calculated=False`` edits made outside punches) are
not touched, and no punch is ever invented: sessions without an OUT
stay open by design.

Usage (from the repo root, on the machine whose TIME_ZONE matches the
deployment timezone — punch day boundaries are localtime):

    python manage.py shell < scripts/replay_worksessions.py

Environment knobs (REPLAY_SINCE is required, windows never auto-grow):

    REPLAY_TENANT   tenant schema to process (default: freshline)
    REPLAY_SINCE    start day YYYY-MM-DD — REQUIRED. No auto window:
                    deriving the window from surviving open sessions
                    lets committed re-runs replay older days that were
                    never reset, so every run pins its window.
    REPLAY_UNTIL    end day YYYY-MM-DD (inclusive); default: today
    REPLAY_DRYRUN   1 = replay, print the would-be state, roll back
    REPLAY_RESET    1 = destroy the window's derived state first:
                    delete WorkSession/BreakSession rows with
                    day in [SINCE, UNTIL], clear attendance links on
                    punch rows in the window, then replay from a clean
                    state. Attendance day rows are kept and re-stamped.
                    TAKE A DB DUMP BEFORE RUNNING THIS VIA SERVER.
"""

import os
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from django_tenants.utils import get_tenant_model, tenant_context

from attendance.models import (
    Attendance,
    AttendanceActivity,
    BreakSession,
    WorkSession,
)
from attendance.services import attendance_update_for_punch
from employees.models import Employee

TENANT = os.getenv("REPLAY_TENANT", "freshline")
DRYRUN = os.getenv("REPLAY_DRYRUN", "0") == "1"
RESET = os.getenv("REPLAY_RESET", "0") == "1"

STATE = {"rows": 0, "sessions": 0, "create_calls": 0, "summary": []}


def _date_env_or_none(name):
    raw = os.getenv(name)
    return date.fromisoformat(raw) if raw else None


def snapshot(window_punches, start, until_plus_one):
    return {
        "punches": window_punches.count(),
        "rows": Attendance.objects.filter(
            day__gte=start, day__lt=until_plus_one
        ).count(),
        "sessions": WorkSession.objects.filter(day__gte=start).count(),
        "open_sessions": WorkSession.objects.filter(check_out__isnull=True).count(),
    }


def replay_employee(employee, activities, qa):
    before = len(activities)
    for activity in activities:
        attendance_update_for_punch(
            employee=employee,
            punch_time=activity.punch_time,
            direction=activity.direction,
            activity=activity,
        )
        STATE["create_calls"] += 1
    sessions = WorkSession.objects.filter(employee=employee, day__gte=SINCE)
    open_count = sessions.filter(check_out__isnull=True).count()
    rows = Attendance.objects.filter(
        employee=employee, day__gte=SINCE, day__lte=UNTIL
    ).order_by("day")

    def row_bit(r):
        check_in = (
            timezone.localtime(r.check_in, qa).strftime("%H:%M")
            if r.check_in else "--"
        )
        check_out = (
            "->" + timezone.localtime(r.check_out, qa).strftime("%H:%M")
            if r.check_out else "open"
        )
        return f"{r.day:%d} {r.status} {check_in}{check_out}"

    name = f"{employee.emp_code} {employee.first_name} {employee.last_name}"
    STATE["summary"].append(
        f"  {name[:45]:<45} punches={before:<4} "
        f"sessions={sessions.count():<3} open={open_count:<2} rows: "
        + ", ".join(row_bit(r) for r in rows)
    )


t = get_tenant_model().objects.get(schema_name=TENANT)

with tenant_context(t):
    qa = timezone.get_current_timezone()
    UNTIL = _date_env_or_none("REPLAY_UNTIL") or timezone.localdate()
    until_plus_one = UNTIL + timedelta(days=1)

    SINCE = _date_env_or_none("REPLAY_SINCE")
    if SINCE is None:
        raise SystemExit(
            "REPLAY_SINCE is required (e.g. REPLAY_SINCE=2026-10-28). "
            "Windows are pinned per run — no auto derivation."
        )
    if SINCE > UNTIL:
        SINCE = UNTIL

    before = snapshot(
        AttendanceActivity.objects.filter(
            punch_time__date__gte=SINCE, punch_time__date__lte=UNTIL
        ),
        SINCE,
        until_plus_one,
    )

    print(f"[replay] tenant={TENANT} window {SINCE}..{UNTIL} "
          f"({'DRYRUN' if DRYRUN else 'WRITE'}{', RESET' if RESET else ''})")
    print(f"[replay] before: {before}")

    with transaction.atomic():
        if RESET:
            ws_deleted = WorkSession.objects.filter(
                day__gte=SINCE, day__lte=UNTIL
            )
            ws_count = ws_deleted.count()
            bs_count = BreakSession.objects.filter(
                day__gte=SINCE, day__lte=UNTIL
            ).count()
            print(f"[reset] deleting {ws_count} WorkSessions + "
                  f"{bs_count} BreakSessions in window")
            ws_deleted.delete()
            BreakSession.objects.filter(
                day__gte=SINCE, day__lte=UNTIL
            ).delete()
            links = (
                AttendanceActivity.objects
                .filter(punch_time__date__gte=SINCE)
                .filter(punch_time__date__lte=UNTIL)
            )
            print(f"[reset] clearing attendance links on "
                  f"{links.count()} punches")
            links.update(attendance=None)
            stamped = Attendance.objects.filter(
                day__gte=SINCE, day__lte=UNTIL
            )
            print(f"[reset] clearing derived times on "
                  f"{stamped.count()} Attendance rows (status kept)")
            stamped.update(
                check_in=None, check_out=None, total_work_time=timedelta(0)
            )
        else:
            ws_count = bs_count = 0
        if RESET:
            print(f"[reset] deleted {ws_count} WorkSessions, "
                  f"{bs_count} BreakSessions")
        employee_ids = set(
            AttendanceActivity.objects.filter(
                punch_time__date__gte=SINCE, punch_time__date__lte=UNTIL
            ).values_list("employee_id", flat=True)
        )
        for employee_id in sorted(employee_ids):
            activities = (
                AttendanceActivity.objects
                .filter(employee_id=employee_id)
                .filter(punch_time__date__gte=SINCE)
                .filter(punch_time__date__lte=UNTIL)
                .order_by("punch_time")
            )
            replay_employee_rec = activities.select_related("attendance")
            employee = Employee.objects.get(pk=employee_id)
            replay_employee(employee, list(replay_employee_rec), qa)

        after = snapshot(
            AttendanceActivity.objects.filter(
                punch_time__date__gte=SINCE, punch_time__date__lte=UNTIL
            ),
            SINCE,
            until_plus_one,
        )
        unlinked = (
            AttendanceActivity.objects.filter(attendance__isnull=True)
            .filter(punch_time__date__gte=SINCE)
            .exclude(direction="unknown")
            .count()
        )
        print()
        print("\n".join(STATE["summary"]))
        print()
        print(f"[replay] after: {after}")
        print(f"[replay] punch-pairing calls: {STATE['create_calls']}, "
              f"unlinked punches in window: {unlinked}")
        if DRYRUN:
            print("[replay] DRYRUN — rolling back")
            transaction.set_rollback(True)
        else:
            print("[replay] committed")

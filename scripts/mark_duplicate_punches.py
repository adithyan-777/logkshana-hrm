"""Apply the duplicate-punch ignore rules to the punch log — shell mode.

Recomputes ``AttendanceActivity.ignored`` for every effective punch
(everything except already-corrected originals) using the SAME rule the
pairing engine applies at ingest (``punch_is_duplicate``):

- an IN while a session is already open on the same day  -> ignored=True
- an OUT with no open session to close (already out)     -> ignored=True
- break/overtime/unknown directions and correction rows that pair
  normally are left at their recomputed value by the same rule.

This is a FLAGGING pass only: it never touches WorkSessions, daily
Attendance rows, or pairing — the log flags reflect the intended
state after the fact. If you also want the day's pairing re-derived
to match the flags, run scripts/replay_worksessions.py separately.

Usage (from the repo root):

    DJANGO_SETTINGS_MODULE=config.settings python manage.py shell \\
        < scripts/mark_duplicate_punches.py

Environment knobs (all optional):

    MARK_TENANT   tenant schema (default: freshline)
    MARK_SINCE    start day YYYY-MM-DD (inclusive), default: no limit
    MARK_UNTIL    end day YYYY-MM-DD (inclusive), default: no limit
    MARK_EMP      emp_code to restrict to one employee
    MARK_DRYRUN   1 = compute + print, roll back, write nothing
"""
import os

from django_tenants.utils import get_tenant_model, tenant_context

from attendance.models import AttendanceActivity
from attendance.services import punch_is_duplicate

TENANT = os.getenv("MARK_TENANT", "freshline")
SINCE = os.getenv("MARK_SINCE")
UNTIL = os.getenv("MARK_UNTIL")
EMP = os.getenv("MARK_EMP")
DRYRUN = os.getenv("MARK_DRYRUN", "0") == "1"


def _stats(bulk: dict, employee, *, flagged: int, unflagged: int) -> None:
    if flagged or unflagged:
        name = f"{employee.emp_code} {employee.full_name}"
        print(f"  {name[:40]:<40} flagged={flagged:<4} cleared={unflagged}")


tenant = get_tenant_model().objects.get(schema_name=TENANT)

with tenant_context(tenant):

    qs = AttendanceActivity.objects.filter(corrected_punch__isnull=True)
    if SINCE:
        qs = qs.filter(punch_time__date__gte=SINCE)
    if UNTIL:
        qs = qs.filter(punch_time__date__lte=UNTIL)
    if EMP:
        qs = qs.filter(employee__emp_code=EMP)

    punches = list(
        qs.select_related("employee").order_by("employee_id", "punch_time", "pk")
    )
    if not punches:
        print(f"[mark] nothing to process for tenant={TENANT}")
        raise SystemExit(0)

    total_flagged = total_cleared = 0
    per_employee: dict = {}
    for activity in punches:
        ignored = punch_is_duplicate(
            employee=activity.employee,
            punch_day=activity.punch_time.date(),
            direction=activity.direction,
        )
        if activity.ignored != ignored:
            activity.ignored = ignored
            if not DRYRUN:
                activity.save(update_fields=["ignored", "updated_at"])
            stats = per_employee.setdefault(activity.employee, [0, 0])
            stats[0 if ignored else 1] += 1
            if ignored:
                total_flagged += 1
            else:
                total_cleared += 1

    print(
        f"[mark] tenant={TENANT} punches={len(punches)} "
        f"{'DRYRUN' if DRYRUN else 'WRITE'} -> "
        f"flagged={total_flagged} cleared={total_cleared}"
    )
    for employee, (flagged, unflagged) in sorted(
        per_employee.items(), key=lambda item: item[0].emp_code
    ):
        _stats({}, employee, flagged=flagged, unflagged=unflagged)
    if DRYRUN:
        print("[mark] DRYRUN — nothing written")

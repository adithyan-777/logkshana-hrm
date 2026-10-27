from policies.models import AttendancePolicy


def attendance_policy_get() -> AttendancePolicy | None:
    """The tenant's single AttendancePolicy.

    One row per company (tenant schema). Missing row is treated as
    the default ``scheduled`` mode — callers must handle ``None``
    rather than implicitly creating the policy.
    """
    return AttendancePolicy.objects.first()


def attendance_policy_is_unscheduled() -> bool:
    """True when punch-based (check-in/check-out) calculation applies."""
    policy = attendance_policy_get()
    return policy is not None and (
        policy.schedule_mode == AttendancePolicy.ScheduleMode.UNSCHEDULED
    )

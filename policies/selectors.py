from policies.models import AttendancePolicy, UnscheduledConfig


def attendance_policy_get() -> AttendancePolicy | None:
    """The tenant's single AttendancePolicy.

    One row per company (tenant schema). Missing row is treated as
    the default ``scheduled`` mode — callers must handle ``None``
    rather than implicitly creating the config.
    """
    return AttendancePolicy.objects.first()


def attendance_policy_is_unscheduled() -> bool:
    """True when punch-based (check-in/check-out) calculation applies."""
    policy = attendance_policy_get()
    return policy is not None and (
        policy.schedule_mode == AttendancePolicy.ScheduleMode.UNSCHEDULED
    )


def unscheduled_config_get() -> UnscheduledConfig | None:
    """The tenant's single UnscheduledConfig (opening/closing hours).

    One row per company (tenant schema). Missing row or null times
    means "no day boundary configured" — callers fall back to
    unbounded behavior.
    """
    return UnscheduledConfig.objects.first()


def unscheduled_opening_time_get():
    """The tenant's day-boundary time (UnscheduledConfig.opening_time).

    The day boundary for punch pairing: a next-day check-out counts
    as the previous day's overnight wrap only earlier than this —
    past it the punch is the new day's stray check-out. Missing
    config or a null opening_time means no day boundary.
    """
    config = unscheduled_config_get()
    return config.opening_time if config is not None else None

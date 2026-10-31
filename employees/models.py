from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from common.models import BaseModel
from companies.models import Branch


class Department(BaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    def __str__(self):
        return self.name


class Position(BaseModel):
    title = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    def __str__(self):
        return self.title


class Permission(BaseModel):
    codename = models.CharField(
        max_length=100
    )  # "view_department_employees"
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "codename",
                name="uniq_permission_codename_alive",
            ),
        ]

    def __str__(self):
        return self.codename


class Role(BaseModel):
    name = models.CharField(max_length=50)
    is_system = models.BooleanField(
        default=False
    )  # protects built-in roles from deletion
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "name",
                name="uniq_role_name_alive",
            ),
        ]

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValidationError(
                {"is_system": "Built-in roles cannot be deleted."}
            )
        return super().delete(*args, **kwargs)


class Area(BaseModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    def __str__(self):
        return self.name


class EmployeePunchStatus(models.TextChoices):
    """Live punch-state values mirrored from ``AttendanceActivity``.

    Values are *identical* to the punch ``Direction`` values they mirror, so
    the stored field is a faithful copy of the employee's latest punch. The
    empty string means "never punched" (and unknown-direction punches are
    never mirrored — they carry no meaningful state).
    """

    CHECK_IN = "in", "Checked in"
    CHECK_OUT = "out", "Checked out"
    BREAK_IN = "break_in", "On break"
    BREAK_OUT = "break_out", "Back from break"
    OVERTIME_IN = "overtime_in", "On overtime"
    OVERTIME_OUT = "overtime_out", "Overtime ended"


class EmployeeType(models.TextChoices):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"
    TEMPORARY = "temporary"
    VOLUNTEER = "volunteer"


class Employee(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile",
    )
    emp_code = models.CharField(max_length=50, blank=True, null=True, unique=True)

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)

    employee_type = models.CharField(
        max_length=50, choices=EmployeeType.choices, default=EmployeeType.FULL_TIME
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )

    role = models.ForeignKey(
        Role, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees"
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )

    email = models.EmailField(blank=True)
    mobile = models.CharField(max_length=30, blank=True)

    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # Denormalized mirror of the employee's latest punch (direction +
    # timestamp), refreshed by ``employee_punch_status_recompute`` at every
    # punch write path (create/update/delete/replay). Deriving on read kept
    # the badges honest but cost queries per row; this field is always
    # recomputed *from* the punch log, so it edits cheaply and a repair
    # pass can re-derive it wholesale — the log stays the source of truth.
    punch_status = models.CharField(
        max_length=12,
        choices=EmployeePunchStatus.choices,
        blank=True,
        default="",
        help_text="Mirrored direction of the employee's latest punch.",
    )
    punch_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the employee's latest mirrored punch.",
    )

    class Meta:
        # Per-tenant table, so this is automatically per-tenant.
        # Case-insensitive, blank exempt ("" means "no email").
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="uniq_employee_email_ci",
                condition=~Q(email=""),
            ),
        ]

    def clean(self):
        super().clean()
        # Blank/whitespace-only codes mean "no code" and must not create
        # distinct rows that only differ by padding.
        self.emp_code = (self.emp_code or "").strip() or None

    def __str__(self):
        parts = [part for part in (self.emp_code, self.full_name) if part]
        return " - ".join(parts) or "Employee"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def has_punch(self) -> bool:
        """True once the employee has a mirrored (non-unknown) punch."""
        return bool(self.punch_status)

    @property
    def punch_display_time(self) -> str:
        """HH:MM of the mirrored punch, in tenant local time.

        Punches are stored aware (UTC) like every other timestamp; the
        badge must display the same wall-clock the punch log shows
        (``TIME_ZONE``), so aware values are localized before manual
        ``strftime`` — a raw ``strftime`` would print UTC hours.
        """
        if self.punch_time is None:
            return ""
        from django.utils import timezone

        value = self.punch_time
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime("%H:%M")

    @property
    def next_punch_direction(self) -> str:
        """The punch a web-punch toggle should record next.

        Inverse state machine over the mirrored status: IN-record opens
        work, ..._IN records close their sub-period first (a break-mode
        click ends the break, overtime ends overtime), and back-from-x
        or closed states re-open work. "Punched out ⇒ next is in, and
        vice versa" is simply the top-level rule of this mapping.
        """
        # Values of the mirror mirror the punch Direction vocabulary,
        # but the enum lives in attendance (which imports schedule,
        # which imports this module) — import lazily to stay
        # import-cycle-free.
        from attendance.models import AttendanceActivity

        _NEXT_PUNCH_DIRECTION = {
            EmployeePunchStatus.CHECK_IN: AttendanceActivity.Direction.OUT,
            EmployeePunchStatus.CHECK_OUT: AttendanceActivity.Direction.IN,
            EmployeePunchStatus.BREAK_IN: AttendanceActivity.Direction.BREAK_OUT,
            EmployeePunchStatus.BREAK_OUT: AttendanceActivity.Direction.OUT,
            EmployeePunchStatus.OVERTIME_IN: AttendanceActivity.Direction.OVERTIME_OUT,
            EmployeePunchStatus.OVERTIME_OUT: AttendanceActivity.Direction.OUT,
            "": AttendanceActivity.Direction.IN,
        }
        return _NEXT_PUNCH_DIRECTION[self.punch_status]

    @property
    def punch_action_label(self) -> str:
        """Hover label of the toggle for the current mirror state."""
        _LABELS = {
            EmployeePunchStatus.CHECK_IN: "Punch out",
            EmployeePunchStatus.CHECK_OUT: "Punch in",
            EmployeePunchStatus.BREAK_IN: "End break",
            EmployeePunchStatus.BREAK_OUT: "Punch out",
            EmployeePunchStatus.OVERTIME_IN: "End overtime",
            EmployeePunchStatus.OVERTIME_OUT: "Punch out",
            "": "Punch in",
        }
        return _LABELS[self.punch_status]

    @property
    def initials(self):
        """Two-letter round-avatar initials: first+last, else first-two, else code/email, else ?."""
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        if first and last:
            return f"{first[0]}{last[0]}".upper()
        if first or last:
            word = first or last
            return (word[:2] if len(word) > 1 else word[0]).upper()
        for fallback in (self.emp_code or "", self.email or ""):
            cleaned = "".join(ch for ch in fallback if ch.isalnum())
            if cleaned:
                return cleaned[:2].upper()
        return "?"

    @property
    def avatar_variant(self):
        """Stable 0-7 color variant derived from the display name."""
        import hashlib

        seed = (self.full_name or self.emp_code or self.email or "?").lower()
        digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
        return int(digest[:2], 16) % 8

from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone
from django_tenants.utils import (
    get_public_schema_name,
    get_tenant_model,
    schema_context,
    schema_exists,
)

from companies.models import Company, Domain
from companies.services import company_primary_branch_get_or_create

from attendance.models import (
    AttendanceCorrection,
    AttendanceRule,
    AttendanceTransaction,
    DailyAttendance,
)
from attendance.services import (
    attendance_correction_create,
    attendance_rule_create,
    attendance_transaction_create,
    daily_attendance_create,
)
from employees.models import Department, Employee, Position
from employees.services import employee_create
from leave.models import Holiday, LeavePolicy, LeaveRequest, LeaveType
from leave.services import (
    holiday_create,
    leave_policy_create,
    leave_request_create,
    leave_type_create,
)
from schedule.models import ScheduleAssignment, Shift, Timetable
from schedule.services import (
    schedule_assignment_create,
    shift_create,
    timetable_create,
)


def _get_or_create_department(*, name: str, code: str) -> Department:
    department = Department.objects.filter(code=code).first()
    if department:
        return department

    department = Department(name=name, code=code)
    department.full_clean()
    department.save()
    return department


def _get_or_create_position(*, title: str, code: str) -> Position:
    position = Position.objects.filter(code=code).first()
    if position:
        return position

    position = Position(title=title, code=code)
    position.full_clean()
    position.save()
    return position


def _get_or_create_employee(
    *,
    first_name: str,
    last_name: str,
    emp_code: str,
    department=None,
    position=None,
    email: str = "",
    hire_date=None,
    branch=None,
) -> Employee:
    employee = Employee.objects.filter(emp_code=emp_code).first()
    if employee:
        if branch is not None and employee.branch_id is None:
            employee.branch = branch
            employee.save(update_fields=["branch"])
        return employee

    employee = employee_create(
        first_name=first_name,
        last_name=last_name,
        emp_code=emp_code,
        department=department,
        position=position,
        email=email,
        hire_date=hire_date,
        sync_to_device=False,
    )
    if branch is not None:
        employee.branch = branch
        employee.save(update_fields=["branch"])
    return employee


def _get_or_create_timetable(*, name: str, code: str, **kwargs) -> Timetable:
    timetable = Timetable.objects.filter(code=code).first()
    if timetable:
        return timetable

    defaults = {
        "type": Timetable.Type.NORMAL,
        "work_type": Timetable.WorkType.WORK,
        "check_in": time(9, 0),
        "check_out": time(18, 0),
        "late_in_grace_minutes": 10,
        "early_out_grace_minutes": 5,
        "is_active": True,
    }
    defaults.update(kwargs)
    return timetable_create(name=name, code=code, **defaults)


def _get_or_create_shift(*, name: str, code: str, shift_days: list[dict]) -> Shift:
    shift = Shift.objects.filter(code=code).first()
    if shift:
        return shift

    return shift_create(
        name=name,
        code=code,
        cycle_unit="week",
        cycle_count=1,
        is_active=True,
        shift_days=shift_days,
    )


def seed_demo_data(*, branch=None) -> dict[str, int]:
    """Populate the current tenant schema with demo HR data."""
    created = {
        "departments": 0,
        "positions": 0,
        "employees": 0,
        "timetables": 0,
        "shifts": 0,
        "assignments": 0,
        "leave_types": 0,
        "leave_policies": 0,
        "holidays": 0,
        "leave_requests": 0,
        "attendance_rules": 0,
        "attendance_transactions": 0,
        "daily_attendance": 0,
        "attendance_corrections": 0,
    }

    def count_if_new(before, after, key):
        if after > before:
            created[key] += after - before

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------
    before = Department.objects.count()
    engineering = _get_or_create_department(name="Engineering", code="DEMO-ENG")
    hr = _get_or_create_department(name="Human Resources", code="DEMO-HR")
    finance = _get_or_create_department(name="Finance", code="DEMO-FIN")
    count_if_new(before, Department.objects.count(), "departments")

    before = Position.objects.count()
    developer = _get_or_create_position(title="Software Developer", code="DEMO-DEV")
    hr_manager = _get_or_create_position(title="HR Manager", code="DEMO-HRM")
    accountant = _get_or_create_position(title="Accountant", code="DEMO-ACC")
    count_if_new(before, Position.objects.count(), "positions")

    hire_date = date(2024, 1, 15)
    before = Employee.objects.count()
    ahmed = _get_or_create_employee(
        first_name="Ahmed",
        last_name="Al-Rashid",
        emp_code="DEMO-001",
        department=engineering,
        position=developer,
        email="ahmed.demo@example.com",
        hire_date=hire_date,
        branch=branch,
    )
    fatima = _get_or_create_employee(
        first_name="Fatima",
        last_name="Hassan",
        emp_code="DEMO-002",
        department=hr,
        position=hr_manager,
        email="fatima.demo@example.com",
        hire_date=hire_date,
        branch=branch,
    )
    omar = _get_or_create_employee(
        first_name="Omar",
        last_name="Khalid",
        emp_code="DEMO-003",
        department=finance,
        position=accountant,
        email="omar.demo@example.com",
        hire_date=hire_date,
        branch=branch,
    )
    sara = _get_or_create_employee(
        first_name="Sara",
        last_name="Ali",
        emp_code="DEMO-004",
        department=engineering,
        position=developer,
        email="sara.demo@example.com",
        hire_date=date(2025, 3, 1),
        branch=branch,
    )
    count_if_new(before, Employee.objects.count(), "employees")

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------
    before = Timetable.objects.count()
    morning = _get_or_create_timetable(
        name="Demo Morning",
        code="DEMO-MORN",
        check_in=time(9, 0),
        check_out=time(18, 0),
    )
    evening = _get_or_create_timetable(
        name="Demo Evening",
        code="DEMO-EVE",
        check_in=time(14, 0),
        check_out=time(22, 0),
    )
    day_off = _get_or_create_timetable(
        name="Demo Day Off",
        code="DEMO-OFF",
        work_type=Timetable.WorkType.OFF,
        check_in=None,
        check_out=None,
    )
    count_if_new(before, Timetable.objects.count(), "timetables")

    before = Shift.objects.count()
    standard_week = _get_or_create_shift(
        name="Demo Standard Week",
        code="DEMO-WEEK",
        shift_days=[
            {
                "day_number": day_number,
                "timetable": morning if day_number <= 5 else day_off,
            }
            for day_number in range(1, 8)
        ],
    )
    count_if_new(before, Shift.objects.count(), "shifts")

    assignment_start = date(2026, 1, 1)
    assignment_end = date(2026, 12, 31)
    before = ScheduleAssignment.objects.count()

    if not ScheduleAssignment.objects.filter(
        assignment_type=ScheduleAssignment.AssignmentType.DEPARTMENT,
        department=engineering,
        shift=standard_week,
    ).exists():
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.DEPARTMENT,
            shift=standard_week,
            start_date=assignment_start,
            end_date=assignment_end,
            department=engineering,
        )

    for employee in (ahmed, sara):
        if not ScheduleAssignment.objects.filter(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            employee=employee,
            shift=standard_week,
        ).exists():
            schedule_assignment_create(
                assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
                shift=standard_week,
                start_date=assignment_start,
                end_date=assignment_end,
                employee=employee,
            )

    if not ScheduleAssignment.objects.filter(
        assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
        employee=fatima,
        shift=standard_week,
    ).exists():
        evening_shift = _get_or_create_shift(
            name="Demo Evening Week",
            code="DEMO-EVE-WEEK",
            shift_days=[
                {
                    "day_number": day_number,
                    "timetable": evening if day_number <= 5 else day_off,
                }
                for day_number in range(1, 8)
            ],
        )
        schedule_assignment_create(
            assignment_type=ScheduleAssignment.AssignmentType.EMPLOYEE,
            shift=evening_shift,
            start_date=assignment_start,
            end_date=assignment_end,
            employee=fatima,
        )

    count_if_new(before, ScheduleAssignment.objects.count(), "assignments")

    # ------------------------------------------------------------------
    # Leave
    # ------------------------------------------------------------------
    before = LeaveType.objects.count()
    annual = LeaveType.objects.filter(code="DEMO-ANNUAL").first()
    if not annual:
        annual = leave_type_create(
            name="Annual Leave",
            code="DEMO-ANNUAL",
            description="Paid annual leave",
        )
    sick = LeaveType.objects.filter(code="DEMO-SICK").first()
    if not sick:
        sick = leave_type_create(
            name="Sick Leave",
            code="DEMO-SICK",
            description="Paid sick leave",
        )
    count_if_new(before, LeaveType.objects.count(), "leave_types")

    before = LeavePolicy.objects.count()
    if not LeavePolicy.objects.filter(name="Demo Annual Policy").exists():
        leave_policy_create(
            leave_type=annual,
            name="Demo Annual Policy",
            entitlement_days=30,
            accrual_type=LeavePolicy.AccrualType.YEARLY,
        )
    if not LeavePolicy.objects.filter(name="Demo Sick Policy").exists():
        leave_policy_create(
            leave_type=sick,
            name="Demo Sick Policy",
            entitlement_days=10,
            accrual_type=LeavePolicy.AccrualType.YEARLY,
        )
    count_if_new(before, LeavePolicy.objects.count(), "leave_policies")

    before = Holiday.objects.count()
    if not Holiday.objects.filter(name="Demo National Day").exists():
        holiday_create(
            name="Demo National Day",
            date=date(2026, 12, 18),
            holiday_type=Holiday.HolidayType.PUBLIC,
            description="Sample public holiday",
        )
    if not Holiday.objects.filter(name="Demo Company Day").exists():
        holiday_create(
            name="Demo Company Day",
            date=date(2026, 6, 15),
            holiday_type=Holiday.HolidayType.COMPANY,
            description="Sample company holiday",
        )
    count_if_new(before, Holiday.objects.count(), "holidays")

    before = LeaveRequest.objects.count()
    if not LeaveRequest.objects.filter(
        employee=sara,
        start_date=date(2026, 8, 10),
    ).exists():
        leave_request_create(
            employee=sara,
            leave_type=annual,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 14),
            duration_type=LeaveRequest.DurationType.FULL_DAY,
            days=5,
            reason="Family vacation",
            status=LeaveRequest.Status.PENDING,
        )
    count_if_new(before, LeaveRequest.objects.count(), "leave_requests")

    # ------------------------------------------------------------------
    # Attendance
    # ------------------------------------------------------------------
    before = AttendanceRule.objects.count()
    if not AttendanceRule.objects.filter(name="Demo Standard Rule").exists():
        attendance_rule_create(
            name="Demo Standard Rule",
            late_grace_minutes=10,
            early_leave_grace_minutes=5,
            duplicate_punch_window_minutes=2,
        )

    count_if_new(before, AttendanceRule.objects.count(), "attendance_rules")

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    before = AttendanceTransaction.objects.count()
    for employee, punch_date in ((ahmed, today), (sara, today), (omar, yesterday)):
        external_in = f"DEMO-{employee.emp_code}-IN-{punch_date.isoformat()}"
        external_out = f"DEMO-{employee.emp_code}-OUT-{punch_date.isoformat()}"

        if not AttendanceTransaction.objects.filter(external_id=external_in).exists():
            check_in = timezone.make_aware(datetime.combine(punch_date, time(9, 5)))
            attendance_transaction_create(
                employee=employee,
                external_id=external_in,
                timestamp=check_in,
                direction=AttendanceTransaction.Direction.IN,
                source=AttendanceTransaction.Source.BIOMETRIC,
            )

        if not AttendanceTransaction.objects.filter(external_id=external_out).exists():
            check_out = timezone.make_aware(datetime.combine(punch_date, time(18, 10)))
            attendance_transaction_create(
                employee=employee,
                external_id=external_out,
                timestamp=check_out,
                direction=AttendanceTransaction.Direction.OUT,
                source=AttendanceTransaction.Source.BIOMETRIC,
            )
    count_if_new(
        before, AttendanceTransaction.objects.count(), "attendance_transactions"
    )

    before = DailyAttendance.objects.count()
    for employee, record_date, status, late in (
        (ahmed, today, DailyAttendance.Status.PRESENT, 5),
        (sara, today, DailyAttendance.Status.LATE, 15),
        (omar, yesterday, DailyAttendance.Status.PRESENT, 0),
        (fatima, yesterday, DailyAttendance.Status.EARLY_OUT, 0),
    ):
        if not DailyAttendance.objects.filter(
            employee=employee, date=record_date
        ).exists():
            daily_attendance_create(
                employee=employee,
                date=record_date,
                status=status,
                shift=standard_week,
                timetable=morning,
                scheduled_minutes=480,
                worked_minutes=465
                if status == DailyAttendance.Status.EARLY_OUT
                else 480,
                late_minutes=late,
                early_leave_minutes=15
                if status == DailyAttendance.Status.EARLY_OUT
                else 0,
                has_check_in=True,
                has_check_out=True,
            )
    count_if_new(before, DailyAttendance.objects.count(), "daily_attendance")

    before = AttendanceCorrection.objects.count()

    if not AttendanceCorrection.objects.filter(
        employee=omar,
        date=yesterday,
        reason="Forgot evening punch",
    ).exists():
        check_in = timezone.make_aware(datetime.combine(yesterday, time(9, 0)))
        attendance_correction_create(
            employee=omar,
            date=yesterday,
            check_in=check_in,
            reason="Forgot evening punch",
            status=AttendanceCorrection.Status.PENDING,
        )
    count_if_new(before, AttendanceCorrection.objects.count(), "attendance_corrections")

    return created


class Command(BaseCommand):
    help = (
        "Seed demo employees, schedule, leave, and attendance data into a "
        "company tenant schema (never public)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            help=(
                "Tenant schema name. Defaults to the only non-public tenant, "
                "or creates schema 'demo' if none exist."
            ),
        )
        parser.add_argument(
            "--domain",
            default="localhost",
            help=(
                "Primary hostname to attach to the seeded tenant. If it "
                "currently belongs to the public tenant, it is moved. "
                "Default: localhost."
            ),
        )
        parser.add_argument(
            "--extra-domains",
            default="",
            help=(
                "Comma-separated additional hostnames to attach, e.g. "
                "'demo.site,shop.example.com'. They must resolve to this "
                "server (DNS or /etc/hosts)."
            ),
        )
        parser.add_argument(
            "--skip-subdomain",
            action="store_true",
            help=(
                "Do not auto-attach the conventional <schema>.TENANT_USERS_DOMAIN "
                "subdomain (e.g. demo.localhost)."
            ),
        )
        parser.add_argument(
            "--owner-email",
            default="demo.owner@example.com",
            help="Email (and username base) of the demo tenant owner to create.",
        )
        parser.add_argument(
            "--owner-password",
            default="ChangeMe123!",
            help=(
                "Initial password for the demo owner. Demo seeding only — "
                "change it immediately after first login."
            ),
        )

    def handle(self, *args, **options):
        public_schema = get_public_schema_name()
        domain = options["domain"]
        verbosity = options.get("verbosity", 1)

        with schema_context(public_schema):
            owner, owner_created = self._ensure_owner(
                email=options["owner_email"],
                password=options["owner_password"],
            )
            tenant, created_tenant = self._resolve_tenant(
                schema_name=options.get("schema"),
                owner=owner,
            )

        self.stdout.write(
            f"Seeding demo data in tenant: {tenant.name} ({tenant.schema_name})"
        )
        if created_tenant:
            self.stdout.write(f"Created tenant '{tenant.schema_name}'")
        if owner_created:
            self.stdout.write(f"Created owner '{owner.email}'")

        self._ensure_tenant_schema(tenant=tenant, verbosity=verbosity)

        hostnames = self._hostnames_for(
            domain=domain,
            schema_name=tenant.schema_name,
            extra_domains=options["extra_domains"],
            skip_subdomain=options["skip_subdomain"],
        )

        with schema_context(public_schema):
            self._ensure_owner_access(owner=owner, tenant=tenant)
            for hostname in hostnames:
                message = self._ensure_domain(tenant=tenant, domain=hostname)
                if message:
                    self.stdout.write(message)
            branch, _ = company_primary_branch_get_or_create(company=tenant)

        with schema_context(tenant.schema_name):
            created = seed_demo_data(branch=branch)

        connection.set_tenant(tenant)

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        for label, count in created.items():
            if count:
                self.stdout.write(f"  created {count} {label.replace('_', ' ')}")

        self.stdout.write("")
        self.stdout.write("Open the app on any of (must resolve to this server):")
        for hostname in hostnames:
            self.stdout.write(f"  http://{hostname}:8000")
        self.stdout.write(
            "Note: *.localhost resolves to 127.0.0.1 on modern systems; "
            "other names need DNS or a /etc/hosts entry."
        )
        self.stdout.write(f"Owner login: {options['owner_email']} (change the seeded password!)")
        self.stdout.write("Sample logins use employee usernames like ahmed.al-rashid")
        self.stdout.write("Demo employee codes: DEMO-001 .. DEMO-004")

    @staticmethod
    def _ensure_owner(*, email: str, password: str):
        """Get or create the demo tenant owner (Company.owner is required)."""
        User = get_user_model()
        username = (email.split("@")[0] or "demo_owner").strip() or "demo_owner"
        owner, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email},
        )
        if created:
            owner.set_password(password)
            owner.save(update_fields=["password"])
        return owner, created

    @staticmethod
    def _ensure_owner_access(*, owner, tenant: Company) -> None:
        """Attach the owner to the tenant with staff rights (admin login)."""
        from tenant_users.permissions.models import UserTenantPermissions

        owner.tenants.add(tenant)
        UserTenantPermissions.objects.update_or_create(
            profile=owner,
            defaults={"is_staff": True},
        )

    def _resolve_tenant(self, *, schema_name: str | None, owner) -> tuple[Company, bool]:
        tenant_model = get_tenant_model()
        public_schema = get_public_schema_name()

        if schema_name:
            if schema_name == public_schema:
                raise CommandError(
                    "Cannot seed demo data into the public schema. "
                    "Public has no employees tables. Pass a company tenant "
                    "with --schema (for example tenant1)."
                )
            try:
                return tenant_model.objects.get(schema_name=schema_name), False
            except tenant_model.DoesNotExist as exc:
                raise CommandError(f"No tenant with schema '{schema_name}'.") from exc

        tenants = list(tenant_model.objects.exclude(schema_name=public_schema))
        if not tenants:
            return self._create_demo_tenant(owner=owner), True
        if len(tenants) > 1:
            names = ", ".join(t.schema_name for t in tenants)
            raise CommandError(
                f"Multiple tenants found ({names}). Pass --schema to choose one."
            )
        return tenants[0], False

    def _create_demo_tenant(self, *, owner) -> Company:
        company = Company(
            schema_name="demo",
            name="Demo Company",
            paid_until=date(2099, 1, 1),
            on_trial=True,
            owner=owner,
        )
        company.save()
        return company

    def _ensure_tenant_schema(self, *, tenant: Company, verbosity: int) -> None:
        if tenant.schema_name == get_public_schema_name():
            raise CommandError("Refusing to migrate or seed the public schema.")

        if not schema_exists(tenant.schema_name):
            self.stdout.write(f"Creating missing schema '{tenant.schema_name}'")
            tenant.create_schema(check_if_exists=True, verbosity=verbosity)
            return

        call_command(
            "migrate_schemas",
            schema_name=tenant.schema_name,
            interactive=False,
            verbosity=verbosity,
        )

    @staticmethod
    def _hostnames_for(
        *,
        domain: str,
        schema_name: str,
        extra_domains: str = "",
        skip_subdomain: bool = False,
    ) -> list[str]:
        """All hostnames to attach to the tenant.

        Besides --domain this includes the conventional
        <schema>.TENANT_USERS_DOMAIN subdomain (e.g. demo.localhost, per
        django-tenant-users' provision_tenant convention), which works
        without any /etc/hosts entry on modern systems.
        """
        hostnames = ["localhost", "127.0.0.1"] if domain == "localhost" else [domain]
        if not skip_subdomain:
            base_domain = getattr(settings, "TENANT_USERS_DOMAIN", None)
            if base_domain:
                conventional = f"{schema_name}.{base_domain}"
                if conventional not in hostnames:
                    hostnames.append(conventional)
        for extra in (extra_domains or "").split(","):
            extra = extra.strip()
            if extra and extra not in hostnames:
                hostnames.append(extra)
        return hostnames

    def _ensure_domain(self, *, tenant: Company, domain: str) -> str | None:
        existing = Domain.objects.filter(domain=domain).select_related("tenant").first()
        has_primary = Domain.objects.filter(tenant=tenant, is_primary=True).exists()

        if existing is None:
            Domain.objects.create(
                domain=domain,
                tenant=tenant,
                is_primary=not has_primary,
            )
            return f"Attached domain {domain} to {tenant.schema_name}"

        if existing.tenant_id == tenant.pk:
            return None

        if existing.tenant.schema_name == get_public_schema_name():
            existing.tenant = tenant
            if not has_primary:
                existing.is_primary = True
            existing.save(update_fields=["tenant", "is_primary"])
            return f"Moved domain {domain} from public to {tenant.schema_name}"

        raise CommandError(
            f"Domain '{domain}' already belongs to tenant "
            f"'{existing.tenant.schema_name}'."
        )

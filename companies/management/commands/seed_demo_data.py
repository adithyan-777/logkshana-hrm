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

from attendance.models import Attendance, AttendanceActivity
from attendance.services import (
    activity_create,
    attendance_record_create,
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
from schedule.models import EmployeeScheduleAssignment, Schedule, Timetable
from schedule.services import schedule_create, timetable_create


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
    mobile: str = "",
    hire_date=None,
    branch=None,
    password: str = "DemoPass123!",
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
        mobile=mobile,
        hire_date=hire_date,
        sync_to_device=False,
        password=password,
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
        "check_in": time(9, 0),
        "check_out": time(18, 0),
        "grace_period_minutes": 10,
        "is_active": True,
    }
    defaults.update(kwargs)
    return timetable_create(name=name, code=code, **defaults)


def _get_or_create_schedule(*, name: str, timetable: Timetable) -> Schedule:
    schedule = Schedule.objects.filter(name=name, timetable=timetable).first()
    if schedule:
        return schedule

    return schedule_create(
        name=name,
        timetable=timetable,
        repeat=True,
        repeat_every=1,
        repeat_unit=Schedule.RepeatUnitType.WEEK,
    )


def seed_demo_data(*, branch=None) -> dict[str, int]:
    """Populate the current tenant schema with demo HR data."""
    created = {
        "departments": 0,
        "positions": 0,
        "employees": 0,
        "timetables": 0,
        "schedules": 0,
        "assignments": 0,
        "leave_types": 0,
        "leave_policies": 0,
        "holidays": 0,
        "leave_requests": 0,
        "attendance_activities": 0,
        "attendance_records": 0,
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
        mobile="+97433000001",
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
        mobile="+97433000002",
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
        mobile="+97433000003",
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
        mobile="+97433000004",
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
    count_if_new(before, Timetable.objects.count(), "timetables")

    before = Schedule.objects.count()
    standard_schedule = _get_or_create_schedule(
        name="Demo Standard Week",
        timetable=morning,
    )
    evening_schedule = _get_or_create_schedule(
        name="Demo Evening Week",
        timetable=evening,
    )
    count_if_new(before, Schedule.objects.count(), "schedules")

    assignment_start = date(2026, 1, 1)
    assignment_end = date(2026, 12, 31)
    before = EmployeeScheduleAssignment.objects.count()

    def _assign(*, name: str, schedule: Schedule, employees: list) -> None:
        assignment = EmployeeScheduleAssignment.objects.filter(
            name=name, schedule=schedule
        ).first()
        if assignment is None:
            assignment = EmployeeScheduleAssignment.objects.create(
                name=name,
                schedule=schedule,
                start_date=assignment_start,
                end_date=assignment_end,
            )
        assignment.employees.add(*employees)

    _assign(
        name="Demo Standard Assignment",
        schedule=standard_schedule,
        employees=[ahmed, sara, omar],
    )
    _assign(
        name="Demo Evening Assignment",
        schedule=evening_schedule,
        employees=[fatima],
    )

    count_if_new(before, EmployeeScheduleAssignment.objects.count(), "assignments")

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
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    before = AttendanceActivity.objects.count()
    for employee, punch_date in ((ahmed, today), (sara, today), (omar, yesterday)):
        external_in = f"DEMO-{employee.emp_code}-IN-{punch_date.isoformat()}"
        external_out = f"DEMO-{employee.emp_code}-OUT-{punch_date.isoformat()}"

        if not AttendanceActivity.objects.filter(external_id=external_in).exists():
            check_in = timezone.make_aware(datetime.combine(punch_date, time(9, 5)))
            activity_create(
                employee=employee,
                punch_time=check_in,
                direction=AttendanceActivity.Direction.IN,
                method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
                external_id=external_in,
            )

        if not AttendanceActivity.objects.filter(external_id=external_out).exists():
            check_out = timezone.make_aware(datetime.combine(punch_date, time(18, 10)))
            activity_create(
                employee=employee,
                punch_time=check_out,
                direction=AttendanceActivity.Direction.OUT,
                method=AttendanceActivity.AttendanceActivityMethodType.BIOMETRIC,
                external_id=external_out,
            )
    count_if_new(
        before, AttendanceActivity.objects.count(), "attendance_activities"
    )

    before = Attendance.objects.count()
    for employee, record_day, status in (
        (ahmed, today, Attendance.Status.PRESENT),
        (sara, today, Attendance.Status.LATE),
        (omar, yesterday, Attendance.Status.PRESENT),
        (fatima, yesterday, Attendance.Status.EARLY_OUT),
    ):
        if not Attendance.objects.filter(
            employee=employee, day=record_day
        ).exists():
            attendance_record_create(
                employee=employee,
                day=record_day,
                status=status,
                shift=morning,
            )
    count_if_new(before, Attendance.objects.count(), "attendance_records")

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
                "Do not auto-attach the conventional <schema>.BASE_DOMAIN "
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
        self.stdout.write(
            f"Owner login: {options['owner_email']} (change the seeded password!)"
        )
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
        tenant.add_user(owner)
        if not owner.is_staff:
            owner.is_staff = True
            owner.save(update_fields=["is_staff"])

    def _resolve_tenant(
        self, *, schema_name: str | None, owner
    ) -> tuple[Company, bool]:
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
        <schema>.BASE_DOMAIN subdomain (e.g. demo.localhost), which works
        without any /etc/hosts entry on modern systems.
        """
        hostnames = ["localhost", "127.0.0.1"] if domain == "localhost" else [domain]
        if not skip_subdomain:
            base_domain = getattr(settings, "BASE_DOMAIN", None)
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

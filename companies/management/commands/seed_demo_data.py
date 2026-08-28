from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from companies.models import Company

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
) -> Employee:
    employee = Employee.objects.filter(emp_code=emp_code).first()
    if employee:
        return employee

    return employee_create(
        first_name=first_name,
        last_name=last_name,
        emp_code=emp_code,
        department=department,
        position=position,
        email=email,
        hire_date=hire_date,
    )


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


def seed_demo_data() -> dict[str, int]:
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
    )
    fatima = _get_or_create_employee(
        first_name="Fatima",
        last_name="Hassan",
        emp_code="DEMO-002",
        department=hr,
        position=hr_manager,
        email="fatima.demo@example.com",
        hire_date=hire_date,
    )
    omar = _get_or_create_employee(
        first_name="Omar",
        last_name="Khalid",
        emp_code="DEMO-003",
        department=finance,
        position=accountant,
        email="omar.demo@example.com",
        hire_date=hire_date,
    )
    sara = _get_or_create_employee(
        first_name="Sara",
        last_name="Ali",
        emp_code="DEMO-004",
        department=engineering,
        position=developer,
        email="sara.demo@example.com",
        hire_date=date(2025, 3, 1),
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
            {"day_number": day_number, "timetable": morning if day_number <= 5 else day_off}
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
                {"day_number": day_number, "timetable": evening if day_number <= 5 else day_off}
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
    count_if_new(before, AttendanceTransaction.objects.count(), "attendance_transactions")

    before = DailyAttendance.objects.count()
    for employee, record_date, status, late in (
        (ahmed, today, DailyAttendance.Status.PRESENT, 5),
        (sara, today, DailyAttendance.Status.LATE, 15),
        (omar, yesterday, DailyAttendance.Status.PRESENT, 0),
        (fatima, yesterday, DailyAttendance.Status.EARLY_OUT, 0),
    ):
        if not DailyAttendance.objects.filter(employee=employee, date=record_date).exists():
            daily_attendance_create(
                employee=employee,
                date=record_date,
                status=status,
                shift=standard_week,
                timetable=morning,
                scheduled_minutes=480,
                worked_minutes=465 if status == DailyAttendance.Status.EARLY_OUT else 480,
                late_minutes=late,
                early_leave_minutes=15 if status == DailyAttendance.Status.EARLY_OUT else 0,
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
    help = "Seed demo employees, schedule, leave, and attendance data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            help="Company name. Defaults to the only company, if exactly one exists.",
        )

    def handle(self, *args, **options):
        company_name = options.get("company")

        if company_name:
            try:
                company = Company.objects.get(name=company_name)
            except Company.DoesNotExist as exc:
                raise CommandError(f"No company named '{company_name}'.") from exc
        else:
            companies = list(Company.objects.all())
            if not companies:
                raise CommandError("No companies found. Create a company first.")
            if len(companies) > 1:
                names = ", ".join(c.name for c in companies)
                raise CommandError(
                    f"Multiple companies found ({names}). Pass --company to choose one."
                )
            company = companies[0]

        self.stdout.write(f"Seeding demo data for {company.name}")

        created = seed_demo_data()

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        for label, count in created.items():
            if count:
                self.stdout.write(f"  created {count} {label.replace('_', ' ')}")

        self.stdout.write("")
        self.stdout.write("Sample logins use employee usernames like ahmed.al-rashid")
        self.stdout.write("Demo employee codes: DEMO-001 .. DEMO-004")

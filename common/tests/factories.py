from datetime import date, time

from employees.models import Department, Position
from employees.services import employee_create
from schedule.models import Timetable
from schedule.services import shift_create, timetable_create


def timetable_factory(*, name="Morning Shift", code="MORN", **kwargs) -> Timetable:
    defaults = {
        "type": Timetable.Type.NORMAL,
        "work_type": Timetable.WorkType.WORK,
        "check_in": time(9, 0),
        "check_out": time(18, 0),
    }
    defaults.update(kwargs)
    return timetable_create(name=name, code=code, **defaults)


def shift_factory(*, name="Week Shift", code="WEEK", timetable=None, **kwargs):
    if timetable is None:
        timetable = timetable_factory(name="Base Shift", code=f"BASE-{code}")

    defaults = {
        "cycle_unit": "week",
        "cycle_count": 1,
        "shift_days": [{"day_number": 1, "timetable": timetable}],
    }
    defaults.update(kwargs)
    return shift_create(name=name, code=code, **defaults)


def department_factory(*, name="Engineering", code="ENG") -> Department:
    department = Department(name=name, code=code)
    department.full_clean()
    department.save()
    return department


def position_factory(*, title="Developer", code="DEV") -> Position:
    position = Position(title=title, code=code)
    position.full_clean()
    position.save()
    return position


def employee_factory(*, first_name="Jane", last_name="Doe", emp_code="E001", **kwargs):
    return employee_create(
        first_name=first_name,
        last_name=last_name,
        emp_code=emp_code,
        **kwargs,
    )


def assignment_dates():
    return date(2026, 1, 1), date(2026, 12, 31)


def leave_type_factory(*, name="Annual Leave", code="ANNUAL", **kwargs):
    from leave.models import LeaveType
    from leave.services import leave_type_create

    defaults = {
        "paid": True,
        "requires_approval": True,
    }
    defaults.update(kwargs)
    return leave_type_create(name=name, code=code, **defaults)


def leave_policy_factory(*, name="Standard Annual", leave_type=None, **kwargs):
    from leave.models import LeavePolicy
    from leave.services import leave_policy_create

    if leave_type is None:
        leave_type = leave_type_factory(name="Policy Leave", code=f"PL-{name[:4].upper()}")

    defaults = {
        "entitlement_days": 30,
        "accrual_type": LeavePolicy.AccrualType.YEARLY,
    }
    defaults.update(kwargs)
    return leave_policy_create(leave_type=leave_type, name=name, **defaults)


def leave_request_factory(*, employee=None, leave_type=None, **kwargs):
    from uuid import uuid4

    from leave.models import LeaveRequest
    from leave.services import leave_request_create

    if employee is None:
        employee = employee_factory(first_name="Leave", emp_code="LR001")
    if leave_type is None:
        leave_type = leave_type_factory(
            name="Sick Leave",
            code=f"SICK-{uuid4().hex[:6]}",
        )

    defaults = {
        "start_date": date(2026, 3, 1),
        "end_date": date(2026, 3, 3),
        "duration_type": LeaveRequest.DurationType.FULL_DAY,
        "days": 3,
        "status": LeaveRequest.Status.PENDING,
    }
    defaults.update(kwargs)
    return leave_request_create(
        employee=employee,
        leave_type=leave_type,
        **defaults,
    )


def holiday_factory(*, name="New Year", **kwargs):
    from leave.models import Holiday
    from leave.services import holiday_create

    defaults = {
        "date": date(2026, 1, 1),
        "holiday_type": Holiday.HolidayType.PUBLIC,
    }
    defaults.update(kwargs)
    return holiday_create(name=name, **defaults)

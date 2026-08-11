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

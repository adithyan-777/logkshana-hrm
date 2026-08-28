from datetime import datetime

from django.core.exceptions import ValidationError

from attendance.models import AttendanceTransaction
from attendance.services import attendance_transaction_create
from companies.models import Branch, Company
from companies.selectors import device_get_by_serial_number
from employees.models import Employee
from employees.selectors import employee_get_by_emp_code

PRIMARY_BRANCH_NAME = "primary"
PRIMARY_BRANCH_CODE = "PRIMARY"


def branch_create(*, name: str, company: Company, code: str | None = None) -> Branch:
    branch = Branch(name=name, company=company, code=code)
    branch.full_clean()
    branch.save()
    return branch


def company_primary_branch_get_or_create(*, company: Company) -> tuple[Branch, bool]:
    branch = Branch.objects.filter(company=company, name=PRIMARY_BRANCH_NAME).first()
    if branch is not None:
        return branch, False

    return (
        branch_create(
            name=PRIMARY_BRANCH_NAME,
            company=company,
            code=PRIMARY_BRANCH_CODE,
        ),
        True,
    )


def companies_ensure_primary_branches(*, companies=None) -> list[dict]:
    """Create a 'primary' branch for each company and assign it to employees without one."""
    if companies is None:
        companies = Company.objects.all()

    results = []
    for company in companies:
        branch, created = company_primary_branch_get_or_create(company=company)
        employees_updated = Employee.objects.filter(branch__isnull=True).update(
            branch=branch
        )

        results.append(
            {
                "company": company,
                "branch": branch,
                "branch_created": created,
                "employees_updated": employees_updated,
            }
        )

    return results


def attendance_log_create(
    *, serial_number: str, employee_id: str, timestamp: datetime
) -> AttendanceTransaction:
    device = device_get_by_serial_number(serial_number=serial_number)
    if device is None:
        raise ValidationError({"serial_number": "Unknown device serial number."})
    if not device.is_active:
        raise ValidationError({"serial_number": "Device is inactive."})

    employee = employee_get_by_emp_code(emp_code=employee_id)
    if employee is None:
        if Employee.objects.filter(emp_code=employee_id, is_active=False).exists():
            raise ValidationError({"employee_id": "Employee is inactive."})
        raise ValidationError({"employee_id": "Unknown employee id."})

    external_id = f"device:{serial_number}:{employee_id}:{timestamp.isoformat()}"
    existing = AttendanceTransaction.objects.filter(external_id=external_id).first()
    if existing is not None:
        return existing

    return attendance_transaction_create(
        employee=employee,
        external_id=external_id,
        timestamp=timestamp,
        direction=AttendanceTransaction.Direction.UNKNOWN,
        source=AttendanceTransaction.Source.BIOMETRIC,
        external_employee_id=employee_id,
        raw_data={
            "serial_number": serial_number,
            "employee_id": employee_id,
            "timestamp": timestamp.isoformat(),
        },
    )

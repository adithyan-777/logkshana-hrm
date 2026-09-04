from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.models import AttendanceTransaction
from attendance.services import attendance_transaction_create
from companies.models import Branch, Company, Device
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
        companies = Company.objects.exclude(schema_name=get_public_schema_name())

    results = []
    for company in companies:
        branch, created = company_primary_branch_get_or_create(company=company)
        employees_updated = 0
        if company.schema_name != get_public_schema_name():
            with schema_context(company.schema_name):
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


def device_sync_state_update(
    *,
    device: Device,
    last_gateway_log_id: int | None = None,
    error: str = "",
) -> Device:
    device.last_synced_at = timezone.now()
    device.last_sync_error = error
    update_fields = ["last_synced_at", "last_sync_error", "updated_at"]
    if last_gateway_log_id is not None:
        device.last_gateway_log_id = last_gateway_log_id
        update_fields.insert(0, "last_gateway_log_id")
    device.save(update_fields=update_fields)
    return device


def attendance_log_create(
    *, serial_number: str, employee_id: str, timestamp: datetime
) -> AttendanceTransaction:
    device = device_get_by_serial_number(serial_number=serial_number)
    if device is None:
        raise ValidationError({"serial_number": "Unknown device serial number."})
    if not device.is_active:
        raise ValidationError({"serial_number": "Device is inactive."})

    with schema_context(device.company.schema_name):
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

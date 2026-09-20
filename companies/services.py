from datetime import datetime

from django.core.exceptions import ValidationError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from attendance.calculation import direction_from_gateway_status
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
    *,
    serial_number: str,
    employee_id: str,
    gateway_log_id: int | str | None = None,
    timestamp: datetime,
    extra_raw_data: dict | None = None,
) -> AttendanceTransaction:
    # Device is a SHARED model (lives in public schema) and the gateway has
    # no tenant context, so the company must always be resolved from the
    # serial number — never from the schema the request happens to be on.
    with schema_context(get_public_schema_name()):
        device = device_get_by_serial_number(serial_number=serial_number)
        if device is None:
            raise ValidationError({"serial_number": "Unknown device serial number."})
        if not device.is_active:
            raise ValidationError({"serial_number": "Device is inactive."})
        # select_related already fetched the company; capture its schema
        # while in public so nothing lazy-loads across contexts.
        tenant_schema = device.company.schema_name
        if tenant_schema == get_public_schema_name():
            raise ValidationError(
                {
                    "serial_number": "Device is assigned to the public schema; reassign it to a real company/tenant."
                }
            )

    with schema_context(tenant_schema):
        employee = employee_get_by_emp_code(emp_code=employee_id)
        if employee is None:
            if Employee.objects.filter(emp_code=employee_id, is_active=False).exists():
                raise ValidationError({"employee_id": "Employee is inactive."})
            raise ValidationError({"employee_id": "Unknown employee id."})

        # Key pushes by the gateway's log id when provided (same scheme as
        # the pull flow, so a log both pushed and pulled never duplicates);
        # otherwise fall back to the deterministic device/employee/time key.
        if gateway_log_id is not None:
            external_id = f"gateway:{gateway_log_id}"
        else:
            external_id = (
                f"device:{serial_number}:{employee_id}:{timestamp.isoformat()}"
            )
        existing = AttendanceTransaction.objects.filter(external_id=external_id).first()
        if existing is not None:
            return existing

        raw_data = {
            "serial_number": serial_number,
            "employee_id": employee_id,
            "timestamp": timestamp.isoformat(),
        }
        if gateway_log_id is not None:
            raw_data["gateway_log_id"] = gateway_log_id
        if extra_raw_data:
            raw_data.update(extra_raw_data)

        # Explicit check-out states from the device close the day's
        # open period; everything else pairs by alternating IN/OUT.
        # Recalculation runs inside attendance_transaction_create, so
        # the employee's DailyAttendance is current before we return.
        direction = direction_from_gateway_status(raw_data.get("status"))

        return attendance_transaction_create(
            employee=employee,
            external_id=external_id,
            timestamp=timestamp,
            direction=direction,
            source=AttendanceTransaction.Source.BIOMETRIC,
            external_employee_id=employee_id,
            raw_data=raw_data,
        )

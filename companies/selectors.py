from django.db import connection
from django.db.models import Q, QuerySet

from companies.models import Branch, Company, Device, DeviceType


def _current_company() -> Company | None:
    tenant = getattr(connection, "tenant", None)
    if tenant is None:
        return None
    if isinstance(tenant, Company):
        return tenant
    return Company.objects.filter(schema_name=connection.schema_name).first()


def device_list(*, search: str = "", company: Company | None = None) -> QuerySet[Device]:
    company = company or _current_company()
    queryset = Device.objects.select_related(
        "company", "branch", "device_type__brand"
    ).order_by("-id")
    if company is not None:
        queryset = queryset.filter(company=company)
    if search:
        queryset = queryset.filter(
            Q(serial_number__icontains=search)
            | Q(name__icontains=search)
            | Q(branch__name__icontains=search)
            | Q(device_type__model_name__icontains=search)
            | Q(device_type__brand__name__icontains=search)
        )
    return queryset


def device_get_by_serial_number(*, serial_number: str) -> Device | None:
    return (
        Device.objects.select_related("company")
        .filter(serial_number=serial_number)
        .first()
    )


def device_get(*, device_id: int, company: Company | None = None) -> Device | None:
    company = company or _current_company()
    queryset = Device.objects.select_related(
        "company", "branch", "device_type__brand"
    )
    if company is not None:
        queryset = queryset.filter(company=company)
    return queryset.filter(pk=device_id).first()


def branch_list(*, search: str = "", company: Company | None = None) -> QuerySet[Branch]:
    company = company or _current_company()
    queryset = Branch.objects.select_related("company").order_by("name")
    if company is not None:
        queryset = queryset.filter(company=company)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(code__icontains=search)
        )
    return queryset


def branch_get(*, branch_id: int, company: Company | None = None) -> Branch | None:
    company = company or _current_company()
    queryset = Branch.objects.select_related("company")
    if company is not None:
        queryset = queryset.filter(company=company)
    return queryset.filter(pk=branch_id).first()


def device_type_list(*, only_active: bool = True) -> QuerySet[DeviceType]:
    queryset = DeviceType.objects.select_related("brand").order_by(
        "brand__name", "model_name"
    )
    if only_active:
        queryset = queryset.filter(is_active=True, brand__is_active=True)
    return queryset

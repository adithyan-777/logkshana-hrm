from companies.models import Device


def device_get_by_serial_number(*, serial_number: str) -> Device | None:
    return (
        Device.objects.select_related("company")
        .filter(serial_number=serial_number)
        .first()
    )

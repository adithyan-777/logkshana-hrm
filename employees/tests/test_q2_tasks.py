from unittest.mock import patch

from django.core.exceptions import ValidationError
from django_tenants.utils import get_public_schema_name, schema_context

from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory
from employees.q2_tasks import create_device_user


class CreateDeviceUserTaskTests(BaseTenantTestCase):
    @patch("employees.services.device_user_create")
    def test_push_delegates_to_service(self, mock_create):
        employee = employee_factory(first_name="Push", emp_code="P001")

        result = create_device_user(self.tenant.schema_name, employee.id, "TEST001")

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        self.assertEqual(call_kwargs["employee"].id, employee.id)
        self.assertEqual(call_kwargs["serial_number"], "TEST001")
        self.assertTrue(result["pushed"])

    @patch("employees.services.device_user_create")
    def test_transient_error_schedules_retry(self, mock_create):
        from django_q.models import Schedule

        employee = employee_factory(first_name="Retry", emp_code="R001")
        mock_create.side_effect = ValidationError(
            {"device": "Gateway returned HTTP 502."}
        )
        with schema_context(get_public_schema_name()):
            before = Schedule.objects.count()
            result = create_device_user(self.tenant.schema_name, employee.id, "TEST001")
            retries = list(Schedule.objects.all()[before:])

        self.assertTrue(result["retried"])
        self.assertEqual(result["attempt"], 1)
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0].func, "employees.q2_tasks.create_device_user")

    @patch("employees.services.device_user_create")
    def test_permanent_error_raises_without_retry(self, mock_create):
        from django_q.models import Schedule

        employee = employee_factory(first_name="Perm", emp_code="E001")
        mock_create.side_effect = ValidationError(
            {"serial_number": "Unknown or inactive device."}
        )
        with schema_context(get_public_schema_name()):
            before = Schedule.objects.count()
            with self.assertRaises(ValidationError):
                create_device_user(self.tenant.schema_name, employee.id, "TEST001")
            after = Schedule.objects.count()

        self.assertEqual(before, after)

    def test_employee_create_enqueues_push_per_device(self):
        from employees.services import employee_create

        device_factory(serial_number="D001", company=self.tenant)
        device_factory(serial_number="D002", company=self.tenant)

        with (
            patch("django_q.tasks.async_task") as mock_async,
            self.captureOnCommitCallbacks(execute=True),
        ):
            employee_create(first_name="Enq", emp_code="ENQ001")

        self.assertEqual(mock_async.call_count, 2)
        serials = {call.args[3] for call in mock_async.call_args_list}
        self.assertEqual(serials, {"D001", "D002"})
        for call in mock_async.call_args_list:
            self.assertEqual(call.args[0], "employees.q2_tasks.create_device_user")
            self.assertEqual(call.args[1], self.tenant.schema_name)

from unittest.mock import patch

from django.core.exceptions import ValidationError

from common.tests.base import BaseTenantTestCase
from common.tests.factories import device_factory, employee_factory
from employees.tasks import create_device_user, delete_device_user


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
    def test_transient_error_raises_for_dramatiq_retry(self, mock_create):
        employee = employee_factory(first_name="Retry", emp_code="R001")
        mock_create.side_effect = ValidationError(
            {"device": "Gateway returned HTTP 502."}
        )

        with self.assertRaises(ValidationError):
            create_device_user(self.tenant.schema_name, employee.id, "TEST001")

    @patch("employees.services.device_user_create")
    def test_permanent_error_returns_without_retry(self, mock_create):
        employee = employee_factory(first_name="Perm", emp_code="E001")
        mock_create.side_effect = ValidationError(
            {"serial_number": "Unknown or inactive device."}
        )

        result = create_device_user(self.tenant.schema_name, employee.id, "TEST001")

        self.assertFalse(result["pushed"])
        self.assertIn("error", result)

    def test_employee_create_enqueues_push_per_device(self):
        from employees.services import employee_create

        device_factory(serial_number="D001", company=self.tenant)
        device_factory(serial_number="D002", company=self.tenant)

        with (
            patch("employees.tasks.create_device_user") as mock_actor,
            self.captureOnCommitCallbacks(execute=True),
        ):
            employee_create(first_name="Enq", emp_code="ENQ001")

        self.assertEqual(mock_actor.send.call_count, 2)
        serials = {call.args[2] for call in mock_actor.send.call_args_list}
        self.assertEqual(serials, {"D001", "D002"})
        for call in mock_actor.send.call_args_list:
            self.assertEqual(call.args[0], self.tenant.schema_name)


class DeleteDeviceUserTaskTests(BaseTenantTestCase):
    @patch("employees.services.device_user_delete")
    def test_delete_delegates_to_service_with_pin(self, mock_delete):
        employee = employee_factory(first_name="Gone", emp_code="G001")

        result = delete_device_user(self.tenant.schema_name, employee.emp_code, "TEST001")

        mock_delete.assert_called_once()
        call_kwargs = mock_delete.call_args.kwargs
        self.assertEqual(call_kwargs["emp_code"], "G001")
        self.assertEqual(call_kwargs["serial_number"], "TEST001")
        self.assertTrue(result["deleted"])

    @patch("employees.services.device_user_delete")
    def test_transient_error_raises_for_dramatiq_retry(self, mock_delete):
        mock_delete.side_effect = ValidationError(
            {"device": "Gateway returned HTTP 502."}
        )

        with self.assertRaises(ValidationError):
            delete_device_user(self.tenant.schema_name, "G001", "TEST001")

    @patch("employees.services.device_user_delete")
    def test_permanent_error_returns_without_retry(self, mock_delete):
        mock_delete.side_effect = ValidationError(
            {"serial_number": "Unknown or inactive device."}
        )

        result = delete_device_user(self.tenant.schema_name, "G001", "TEST001")

        self.assertFalse(result["deleted"])
        self.assertIn("error", result)

    def test_employee_delete_enqueues_removal_per_device(self):
        from employees.services import employee_delete

        device_factory(serial_number="D001", company=self.tenant)
        device_factory(serial_number="D002", company=self.tenant)
        employee = employee_factory(first_name="Leaver", emp_code="LV001")

        with (
            patch("employees.tasks.delete_device_user") as mock_actor,
            self.captureOnCommitCallbacks(execute=True),
        ):
            employee_delete(employee=employee)

        self.assertEqual(mock_actor.send.call_count, 2)
        for call in mock_actor.send.call_args_list:
            self.assertEqual(call.args[0], self.tenant.schema_name)
            self.assertEqual(call.args[1], "LV001")
        serials = {call.args[2] for call in mock_actor.send.call_args_list}
        self.assertEqual(serials, {"D001", "D002"})

    def test_employee_delete_without_pin_enqueues_nothing(self):
        from employees.services import employee_delete

        device_factory(serial_number="D001", company=self.tenant)
        employee = employee_factory(first_name="NoPin", emp_code=None)

        with (
            patch("employees.tasks.delete_device_user") as mock_actor,
            self.captureOnCommitCallbacks(execute=True),
        ):
            employee_delete(employee=employee)

        mock_actor.send.assert_not_called()

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import APIView

from attendance.integrations.gateway import gateway_request_is_authorized
from companies.services import attendance_log_create


@method_decorator(csrf_exempt, name="dispatch")
class AttendanceLogCreateApi(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    class InputSerializer(serializers.Serializer):
        serial_number = serializers.CharField(max_length=100)
        # Canonical pattika field. ``user_id`` is the device-gateway alias
        # (gateway pushes ``{gateway_log_id, serial_number, user_id,
        # timestamp, ...}``). Either id field is accepted; remaining
        # gateway extras (status, verify_mode, work_code) are ignored.
        employee_id = serializers.CharField(max_length=50)
        # Optional gateway log identifier. When present the punch is keyed
        # as ``gateway:<id>`` (same as the pull flow); otherwise it falls
        # back to the device/employee/time key.
        gateway_log_id = serializers.IntegerField(required=False)
        user_id = serializers.CharField(max_length=50, required=False, write_only=True)
        timestamp = serializers.DateTimeField()

        def to_internal_value(self, data):
            if (
                isinstance(data, dict)
                and data.get("user_id")
                and not data.get("employee_id")
            ):
                data = {**data, "employee_id": data["user_id"]}
            return super().to_internal_value(data)

    class OutputSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        external_id = serializers.CharField()
        timestamp = serializers.DateTimeField()
        employee_id = serializers.CharField()
        serial_number = serializers.CharField()

    def post(self, request):
        if not gateway_request_is_authorized(request):
            return Response(
                {"detail": "Invalid or missing gateway credentials."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Future-proofing: forward any extra gateway fields (gateway_id,
        # status, ...) into raw_data untouched, so new gateway fields are
        # stored without needing a code change.
        known_fields = {
            "serial_number",
            "employee_id",
            "user_id",
            "timestamp",
            "gateway_log_id",
        }
        extra_raw_data = None
        if isinstance(request.data, dict):
            extra_raw_data = {
                key: value
                for key, value in request.data.items()
                if key not in known_fields
            } or None

        try:
            punch = attendance_log_create(
                serial_number=serializer.validated_data["serial_number"],
                employee_id=serializer.validated_data["employee_id"],
                gateway_log_id=serializer.validated_data.get("gateway_log_id"),
                timestamp=serializer.validated_data["timestamp"],
                extra_raw_data=extra_raw_data,
            )
        except DjangoValidationError as exc:
            raise DRFValidationError(as_serializer_error(exc))

        data = self.OutputSerializer(
            {
                "id": punch.id,
                "external_id": punch.external_id,
                "timestamp": punch.punch_time,
                "employee_id": punch.employee.emp_code,
                "serial_number": serializer.validated_data["serial_number"],
            }
        ).data
        return Response(data, status=status.HTTP_201_CREATED)

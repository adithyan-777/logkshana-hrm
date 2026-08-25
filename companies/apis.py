from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import APIView

from companies.services import attendance_log_create


@method_decorator(csrf_exempt, name="dispatch")
class AttendanceLogCreateApi(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    class InputSerializer(serializers.Serializer):
        serial_number = serializers.CharField(max_length=100)
        employee_id = serializers.CharField(max_length=50)
        timestamp = serializers.DateTimeField()

    class OutputSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        external_id = serializers.CharField()
        timestamp = serializers.DateTimeField()
        employee_id = serializers.CharField()
        serial_number = serializers.CharField()

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            punch = attendance_log_create(**serializer.validated_data)
        except DjangoValidationError as exc:
            raise DRFValidationError(as_serializer_error(exc))

        data = self.OutputSerializer(
            {
                "id": punch.id,
                "external_id": punch.external_id,
                "timestamp": punch.timestamp,
                "employee_id": punch.external_employee_id,
                "serial_number": serializer.validated_data["serial_number"],
            }
        ).data
        return Response(data, status=status.HTTP_201_CREATED)

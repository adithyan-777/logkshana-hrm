from django.urls import path

from companies.apis import AttendanceLogCreateApi

urlpatterns = [
    path(
        "attendancelog/",
        AttendanceLogCreateApi.as_view(),
        name="attendance-log-create",
    ),
]

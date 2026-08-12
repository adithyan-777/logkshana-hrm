from django.urls import path

from dashboard import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path(
        "partials/attendance-chart/",
        views.dashboard_attendance_chart_partial,
        name="dashboard_attendance_chart_partial",
    ),
]

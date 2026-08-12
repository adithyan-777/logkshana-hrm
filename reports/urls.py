from django.urls import path

from reports import views

urlpatterns = [
    path("", views.report_hub_view, name="report_hub"),
    path("attendance/", views.attendance_summary_view, name="report_attendance_summary"),
    path("individual/", views.individual_attendance_view, name="report_individual_attendance"),
    path("department/", views.department_attendance_view, name="report_department_attendance"),
    path("exceptions/", views.exception_report_view, name="report_exceptions"),
    path("punch-log/", views.punch_log_view, name="report_punch_log"),
    path("overtime/", views.overtime_report_view, name="report_overtime"),
    path("leave/", views.leave_report_view, name="report_leave"),
]

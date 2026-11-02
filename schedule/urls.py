from django.urls import path

from common.feature_flags import Feature, feature_required
from schedule import views

# Every /schedule/... route is gated by the tenant's `schedule` feature
# flag: a tenant that hides Schedule gets 404s on all of these, not just
# a missing sidebar link (see common/feature_flags.py).
urlpatterns = [
    path(route, feature_required(Feature.SCHEDULE)(view), name=name)
    for route, view, name in [
        ("timetables/", views.timetable_list_view, "timetable_list"),
        ("timetables/add/", views.timetable_add, "timetable_add"),
        (
            "timetables/<int:timetable_id>/edit/",
            views.timetable_edit,
            "timetable_edit",
        ),
        (
            "timetables/<int:timetable_id>/delete/",
            views.timetable_delete_view,
            "timetable_delete",
        ),
        ("schedules/", views.schedule_list_view, "schedule_list"),
        ("schedules/add/", views.schedule_add, "schedule_add"),
        (
            "schedules/<int:schedule_id>/edit/",
            views.schedule_edit,
            "schedule_edit",
        ),
        (
            "schedules/<int:schedule_id>/delete/",
            views.schedule_delete_view,
            "schedule_delete",
        ),
        ("assignments/", views.assignment_list_view, "assignment_list"),
        ("assignments/add/", views.assignment_add, "assignment_add"),
        (
            "assignments/<int:assignment_id>/edit/",
            views.assignment_edit,
            "assignment_edit",
        ),
        (
            "assignments/<int:assignment_id>/delete/",
            views.assignment_delete_view,
            "assignment_delete",
        ),
        (
            "by-employee/",
            views.employee_schedule_list_view,
            "employee_schedule_list",
        ),
    ]
]

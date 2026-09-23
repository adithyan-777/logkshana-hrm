from django.urls import path

from schedule import views

urlpatterns = [
    path("timetables/", views.timetable_list_view, name="timetable_list"),
    path("timetables/add/", views.timetable_add, name="timetable_add"),
    path(
        "timetables/<int:timetable_id>/edit/",
        views.timetable_edit,
        name="timetable_edit",
    ),
    path(
        "timetables/<int:timetable_id>/delete/",
        views.timetable_delete_view,
        name="timetable_delete",
    ),
    path("schedules/", views.schedule_list_view, name="schedule_list"),
    path("schedules/add/", views.schedule_add, name="schedule_add"),
    path(
        "schedules/<int:schedule_id>/edit/",
        views.schedule_edit,
        name="schedule_edit",
    ),
    path(
        "schedules/<int:schedule_id>/delete/",
        views.schedule_delete_view,
        name="schedule_delete",
    ),
]

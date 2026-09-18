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
    path("shifts/", views.shift_list_view, name="shift_list"),
    path("shifts/add/", views.shift_add, name="shift_add"),
    path(
        "shifts/<int:shift_id>/edit/",
        views.shift_edit,
        name="shift_edit",
    ),
    path(
        "shifts/<int:shift_id>/delete/",
        views.shift_delete_view,
        name="shift_delete",
    ),
    path("assignments/", views.assignment_list_view, name="assignment_list"),
    path("assignments/add/", views.assignment_add, name="assignment_add"),
    path(
        "assignments/<int:assignment_id>/edit/",
        views.assignment_edit,
        name="assignment_edit",
    ),
    path(
        "assignments/<int:assignment_id>/delete/",
        views.assignment_delete_view,
        name="assignment_delete",
    ),
    path("temporary/", views.temporary_list_view, name="temporary_list"),
    path("temporary/add/", views.temporary_add, name="temporary_add"),
    path(
        "temporary/<int:temporary_id>/edit/",
        views.temporary_edit,
        name="temporary_edit",
    ),
    path(
        "temporary/<int:temporary_id>/delete/",
        views.temporary_delete_view,
        name="temporary_delete",
    ),
]

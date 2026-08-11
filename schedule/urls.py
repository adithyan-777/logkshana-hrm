from django.urls import path

from schedule import views

urlpatterns = [
    path("timetables/", views.timetable_list_view, name="timetable_list"),
    path("timetables/add/", views.timetable_add, name="timetable_add"),
    path("shifts/", views.shift_list_view, name="shift_list"),
    path("shifts/add/", views.shift_add, name="shift_add"),
    path("assignments/", views.assignment_list_view, name="assignment_list"),
    path("assignments/add/", views.assignment_add, name="assignment_add"),
    path("temporary/", views.temporary_list_view, name="temporary_list"),
    path("temporary/add/", views.temporary_add, name="temporary_add"),
]

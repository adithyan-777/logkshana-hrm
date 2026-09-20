from django.urls import path

from leave import views

urlpatterns = [
    path("types/", views.leave_type_list_view, name="leave_type_list"),
    path("types/add/", views.leave_type_add, name="leave_type_add"),
    path(
        "types/<int:leave_type_id>/edit/", views.leave_type_edit, name="leave_type_edit"
    ),
    path(
        "types/<int:leave_type_id>/delete/",
        views.leave_type_delete_view,
        name="leave_type_delete",
    ),
    path("policies/", views.leave_policy_list_view, name="leave_policy_list"),
    path("policies/add/", views.leave_policy_add, name="leave_policy_add"),
    path(
        "policies/<int:leave_policy_id>/edit/",
        views.leave_policy_edit,
        name="leave_policy_edit",
    ),
    path(
        "policies/<int:leave_policy_id>/delete/",
        views.leave_policy_delete_view,
        name="leave_policy_delete",
    ),
    path("requests/", views.leave_request_list_view, name="leave_request_list"),
    path("requests/add/", views.leave_request_add, name="leave_request_add"),
    path(
        "requests/<int:leave_request_id>/edit/",
        views.leave_request_edit,
        name="leave_request_edit",
    ),
    path(
        "requests/<int:leave_request_id>/delete/",
        views.leave_request_delete_view,
        name="leave_request_delete",
    ),
    path("holidays/", views.holiday_list_view, name="holiday_list"),
    path("holidays/add/", views.holiday_add, name="holiday_add"),
    path("holidays/<int:holiday_id>/edit/", views.holiday_edit, name="holiday_edit"),
    path(
        "holidays/<int:holiday_id>/delete/",
        views.holiday_delete_view,
        name="holiday_delete",
    ),
]

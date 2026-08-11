from django.urls import path

from leave import views

urlpatterns = [
    path("types/", views.leave_type_list_view, name="leave_type_list"),
    path("types/add/", views.leave_type_add, name="leave_type_add"),
    path("policies/", views.leave_policy_list_view, name="leave_policy_list"),
    path("policies/add/", views.leave_policy_add, name="leave_policy_add"),
    path("requests/", views.leave_request_list_view, name="leave_request_list"),
    path("requests/add/", views.leave_request_add, name="leave_request_add"),
    path("holidays/", views.holiday_list_view, name="holiday_list"),
    path("holidays/add/", views.holiday_add, name="holiday_add"),
]

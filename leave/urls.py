from django.urls import path

from common.feature_flags import Feature, feature_required
from leave import views

# Every /leave/... route is gated by the tenant's `leave` feature flag:
# a tenant that hides Leave gets 404s on all of these, not just a
# missing sidebar link (see common/feature_flags.py).
urlpatterns = [
    path(route, feature_required(Feature.LEAVE)(view), name=name)
    for route, view, name in [
        ("types/", views.leave_type_list_view, "leave_type_list"),
        ("types/add/", views.leave_type_add, "leave_type_add"),
        (
            "types/<int:leave_type_id>/edit/",
            views.leave_type_edit,
            "leave_type_edit",
        ),
        (
            "types/<int:leave_type_id>/delete/",
            views.leave_type_delete_view,
            "leave_type_delete",
        ),
        ("policies/", views.leave_policy_list_view, "leave_policy_list"),
        ("policies/add/", views.leave_policy_add, "leave_policy_add"),
        (
            "policies/<int:leave_policy_id>/edit/",
            views.leave_policy_edit,
            "leave_policy_edit",
        ),
        (
            "policies/<int:leave_policy_id>/delete/",
            views.leave_policy_delete_view,
            "leave_policy_delete",
        ),
        ("requests/", views.leave_request_list_view, "leave_request_list"),
        ("requests/add/", views.leave_request_add, "leave_request_add"),
        (
            "requests/<int:leave_request_id>/edit/",
            views.leave_request_edit,
            "leave_request_edit",
        ),
        (
            "requests/<int:leave_request_id>/delete/",
            views.leave_request_delete_view,
            "leave_request_delete",
        ),
        ("holidays/", views.holiday_list_view, "holiday_list"),
        ("holidays/add/", views.holiday_add, "holiday_add"),
        (
            "holidays/<int:holiday_id>/edit/",
            views.holiday_edit,
            "holiday_edit",
        ),
        (
            "holidays/<int:holiday_id>/delete/",
            views.holiday_delete_view,
            "holiday_delete",
        ),
    ]
]

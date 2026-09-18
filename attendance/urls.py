from django.urls import path

from attendance import views

urlpatterns = [
    path(
        "transactions/", views.transaction_list_view, name="attendance_transaction_list"
    ),
    path("transactions/add/", views.transaction_add, name="attendance_transaction_add"),
    path(
        "transactions/<int:transaction_id>/edit/",
        views.transaction_edit,
        name="transaction_edit",
    ),
    path(
        "transactions/<int:attendance_transaction_id>/edit/",
        views.attendance_transaction_edit,
        name="attendance_transaction_edit",
    ),
    path(
        "transactions/<int:transaction_id>/delete/",
        views.transaction_delete_view,
        name="transaction_delete",
    ),
    path(
        "transactions/<int:attendance_transaction_id>/delete/",
        views.attendance_transaction_delete_view,
        name="attendance_transaction_delete",
    ),
    path("daily/", views.daily_list_view, name="daily_attendance_list"),
    path("daily/add/", views.daily_add, name="daily_attendance_add"),
    path(
        "daily/<int:daily_id>/edit/",
        views.daily_edit,
        name="daily_edit",
    ),
    path(
        "daily/<int:daily_attendance_id>/edit/",
        views.daily_attendance_edit,
        name="daily_attendance_edit",
    ),
    path(
        "daily/<int:daily_id>/delete/",
        views.daily_delete_view,
        name="daily_delete",
    ),
    path(
        "daily/<int:daily_attendance_id>/delete/",
        views.daily_attendance_delete_view,
        name="daily_attendance_delete",
    ),
    path("corrections/", views.correction_list_view, name="attendance_correction_list"),
    path("corrections/add/", views.correction_add, name="attendance_correction_add"),
    path(
        "corrections/<int:correction_id>/edit/",
        views.correction_edit,
        name="correction_edit",
    ),
    path(
        "corrections/<int:attendance_correction_id>/edit/",
        views.attendance_correction_edit,
        name="attendance_correction_edit",
    ),
    path(
        "corrections/<int:correction_id>/delete/",
        views.correction_delete_view,
        name="correction_delete",
    ),
    path(
        "corrections/<int:attendance_correction_id>/delete/",
        views.attendance_correction_delete_view,
        name="attendance_correction_delete",
    ),
    path("rules/", views.rule_list_view, name="attendance_rule_list"),
    path("rules/add/", views.rule_add, name="attendance_rule_add"),
    path(
        "rules/<int:rule_id>/edit/",
        views.rule_edit,
        name="rule_edit",
    ),
    path(
        "rules/<int:attendance_rule_id>/edit/",
        views.attendance_rule_edit,
        name="attendance_rule_edit",
    ),
    path(
        "rules/<int:rule_id>/delete/",
        views.rule_delete_view,
        name="rule_delete",
    ),
    path(
        "rules/<int:attendance_rule_id>/delete/",
        views.attendance_rule_delete_view,
        name="attendance_rule_delete",
    ),
    path("me/", views.my_attendance_view, name="my_attendance"),
    path("gateway/", views.gateway_view, name="gateway"),
]

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
    path("me/", views.my_attendance_view, name="my_attendance"),
    path("gateway/", views.gateway_view, name="gateway"),
]

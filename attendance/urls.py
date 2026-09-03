from django.urls import path

from attendance import views

urlpatterns = [
    path(
        "transactions/", views.transaction_list_view, name="attendance_transaction_list"
    ),
    path("transactions/add/", views.transaction_add, name="attendance_transaction_add"),
    path("daily/", views.daily_list_view, name="daily_attendance_list"),
    path("daily/add/", views.daily_add, name="daily_attendance_add"),
    path("corrections/", views.correction_list_view, name="attendance_correction_list"),
    path("corrections/add/", views.correction_add, name="attendance_correction_add"),
    path("rules/", views.rule_list_view, name="attendance_rule_list"),
    path("rules/add/", views.rule_add, name="attendance_rule_add"),
    path("me/", views.my_attendance_view, name="my_attendance"),
]

from django.urls import path

from employees import views

urlpatterns = [
    path("", views.employee_list_view, name="employee_list"),
    path("add/", views.employee_add, name="employee_add"),
]

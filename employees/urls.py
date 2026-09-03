from django.urls import path

from employees import views

urlpatterns = [
    path("", views.employee_list_view, name="employee_list"),
    path("add/", views.employee_add, name="employee_add"),
    path("<int:employee_id>/edit/", views.employee_edit, name="employee_edit"),
    path("departments/", views.department_list_view, name="department_list"),
    path("departments/add/", views.department_add, name="department_add"),
    path("positions/", views.position_list_view, name="position_list"),
    path("positions/add/", views.position_add, name="position_add"),
    path("roles/", views.role_list_view, name="role_list"),
    path("roles/add/", views.role_add, name="role_add"),
    path(
        "permissions/",
        views.permission_list_view,
        name="permission_list",
    ),
    path("permissions/add/", views.permission_add, name="permission_add"),
]

from django.urls import path

from employees import views

urlpatterns = [
    path("", views.employee_list_view, name="employee_list"),
    path("add/", views.employee_add, name="employee_add"),
    path("<int:employee_id>/edit/", views.employee_edit, name="employee_edit"),
    path("<int:employee_id>/delete/", views.employee_delete_view, name="employee_delete"),
    path("departments/", views.department_list_view, name="department_list"),
    path("departments/add/", views.department_add, name="department_add"),
    path(
        "departments/<int:department_id>/edit/",
        views.department_edit,
        name="department_edit",
    ),
    path(
        "departments/<int:department_id>/delete/",
        views.department_delete_view,
        name="department_delete",
    ),
    path("positions/", views.position_list_view, name="position_list"),
    path("positions/add/", views.position_add, name="position_add"),
    path(
        "positions/<int:position_id>/edit/",
        views.position_edit,
        name="position_edit",
    ),
    path(
        "positions/<int:position_id>/delete/",
        views.position_delete_view,
        name="position_delete",
    ),
    path("roles/", views.role_list_view, name="role_list"),
    path("roles/add/", views.role_add, name="role_add"),
    path(
        "permissions/",
        views.permission_list_view,
        name="permission_list",
    ),
    path("permissions/add/", views.permission_add, name="permission_add"),
]

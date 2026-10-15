from django.urls import path

from companies import views

urlpatterns = [
    path("", views.device_list_view, name="device_list"),
    path("add/", views.device_add, name="device_add"),
    path("<int:device_id>/edit/", views.device_edit, name="device_edit"),
    path("<int:device_id>/delete/", views.device_delete_view, name="device_delete"),
    path("branches/", views.branch_list_view, name="branch_list"),
    path("branches/add/", views.branch_add, name="branch_add"),
    path(
        "branches/<int:branch_id>/edit/",
        views.branch_edit,
        name="branch_edit",
    ),
    path(
        "branches/<int:branch_id>/delete/",
        views.branch_delete_view,
        name="branch_delete",
    ),
]

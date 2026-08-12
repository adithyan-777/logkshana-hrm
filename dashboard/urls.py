from django.urls import path

from dashboard import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
]

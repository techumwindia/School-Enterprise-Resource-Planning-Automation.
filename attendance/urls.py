from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("", views.mark, name="mark"),
    path("report/", views.report, name="report"),
]

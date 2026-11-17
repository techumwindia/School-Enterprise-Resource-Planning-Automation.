from django.urls import path

from accounts.crud import crud_urls

from . import views

app_name = "academics"

urlpatterns = [
    *crud_urls("year", views.YearViews, prefix="years"),
    *crud_urls("subject", views.SubjectViews, prefix="subjects"),
    *crud_urls("class", views.ClassViews, prefix="classes"),
    path("classes/<int:pk>/", views.class_detail, name="class_detail"),
    path("timetable/", views.timetable, name="timetable"),
    *crud_urls("tt", views.TimetableViews, prefix="timetable/entries"),
]

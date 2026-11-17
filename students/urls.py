from django.urls import path

from accounts.crud import crud_urls

from . import views

app_name = "students"

urlpatterns = [
    *crud_urls("student", views.StudentViews),
    path("<int:pk>/", views.student_detail, name="detail"),
    path("export.csv", views.export_csv, name="export"),
    path("generate-logins/", views.generate_logins, name="generate_logins"),
]

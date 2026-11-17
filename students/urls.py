from django.urls import path

from accounts.crud import crud_urls

from . import views

app_name = "students"

urlpatterns = [
    *crud_urls("student", views.StudentViews),
    path("<int:pk>/", views.student_detail, name="detail"),
    path("<int:pk>/fees/", views.fees_detail, name="fees_detail"),
    path("<int:pk>/attendance/", views.attendance_detail, name="attendance_detail"),
    path("<int:pk>/results/", views.results_detail, name="results_detail"),
    path("<int:pk>/login/", views.login_edit, name="login_edit"),
    path("export.csv", views.export_csv, name="export"),
    path("generate-logins/", views.generate_logins, name="generate_logins"),
]

from django.urls import path

from accounts.crud import crud_urls

from . import views

app_name = "exams"

urlpatterns = [
    *crud_urls("exam", views.ExamViews),
    path("marks/", views.entry, name="entry"),
    path("results/", views.results, name="results"),
    path("report-card/<int:exam_pk>/<int:student_pk>/", views.report_card, name="report_card"),
]

from django.urls import path

from accounts.crud import crud_urls

from . import views

app_name = "staff"

urlpatterns = [
    *crud_urls("staff", views.StaffViews),
    *crud_urls("salary", views.SalaryViews, prefix="salary"),
    path("salary/<int:pk>/payslip/", views.payslip, name="payslip"),
]

from django.urls import path

from accounts.crud import crud_urls

from . import views

app_name = "fees"

urlpatterns = [
    path("", views.collect, name="collect"),
    path("payments/", views.payments, name="payments"),
    path("receipt/<int:pk>/", views.receipt, name="receipt"),
    path("dues/", views.dues, name="dues"),
    *crud_urls("type", views.FeeTypeViews, prefix="types"),
    *crud_urls("structure", views.StructureViews, prefix="structure"),
]

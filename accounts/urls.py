from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .crud import crud_urls

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html",
                                               redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", views.PasswordChange.as_view(), name="password_change"),
    *crud_urls("user", views.UserViews, prefix="users"),
]

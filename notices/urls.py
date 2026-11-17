from django.urls import path

from accounts.crud import crud_urls

from . import views

app_name = "notices"

urlpatterns = [
    path("", views.board, name="board"),
    *crud_urls("notice", views.NoticeViews, prefix="manage"),
    *crud_urls("event", views.EventViews, prefix="events"),
]

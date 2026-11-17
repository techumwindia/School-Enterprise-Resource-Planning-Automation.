from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = settings.SCHOOL_NAME + " — Admin"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("academics/", include("academics.urls")),
    path("students/", include("students.urls")),
    path("staff/", include("staff.urls")),
    path("attendance/", include("attendance.urls")),
    path("fees/", include("fees.urls")),
    path("exams/", include("exams.urls")),
    path("notices/", include("notices.urls")),
    path("", include("accounts.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.contrib import admin

from .models import Attendance

admin.site.register(Attendance, list_display=("student", "date", "status"), list_filter=("date", "status"))

from django.contrib import admin

from .models import Event, Notice

admin.site.register(Notice, list_display=("title", "audience", "publish_date", "is_pinned"))
admin.site.register(Event, list_display=("title", "date", "is_holiday"))

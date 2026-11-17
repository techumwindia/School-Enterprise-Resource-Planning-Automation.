from django.contrib import admin

from .models import Profile

admin.site.register(Profile, list_display=("user", "role", "phone"), list_filter=("role",))

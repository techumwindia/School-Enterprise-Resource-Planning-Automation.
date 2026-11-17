from django.contrib import admin

from .models import Student

admin.site.register(Student, list_display=("admission_no", "full_name", "classroom", "guardian_phone", "is_active"),
                    list_filter=("classroom", "is_active", "gender"), search_fields=("admission_no", "first_name"))

from django.contrib import admin

from .models import Exam, Mark

admin.site.register(Exam, list_display=("name", "academic_year", "is_published"))
admin.site.register(Mark, list_display=("exam", "student", "subject", "marks", "absent"), list_filter=("exam",))

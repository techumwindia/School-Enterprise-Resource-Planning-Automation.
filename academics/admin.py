from django.contrib import admin

from .models import AcademicYear, ClassRoom, Subject, TimetableEntry

admin.site.register(AcademicYear, list_display=("name", "start_date", "end_date", "is_current"))
admin.site.register(Subject, list_display=("name", "code"))
admin.site.register(ClassRoom, list_display=("__str__", "class_teacher", "room_no"))
admin.site.register(TimetableEntry, list_display=("classroom", "day", "period", "subject", "teacher"),
                    list_filter=("classroom", "day"))

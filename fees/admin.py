from django.contrib import admin

from .models import FeePayment, FeeStructure, FeeType

admin.site.register(FeeType)
admin.site.register(FeeStructure, list_display=("academic_year", "classroom", "fee_type", "term", "amount"))
admin.site.register(FeePayment, list_display=("receipt_no", "student", "fee", "amount", "paid_on", "mode"),
                    search_fields=("receipt_no", "student__first_name"))

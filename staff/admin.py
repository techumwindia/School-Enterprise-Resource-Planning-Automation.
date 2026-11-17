from django.contrib import admin

from .models import SalaryPayment, Staff

admin.site.register(Staff, list_display=("employee_id", "name", "designation", "phone", "is_active"),
                    search_fields=("name", "employee_id"))
admin.site.register(SalaryPayment, list_display=("staff", "month", "net_pay", "paid_on"))

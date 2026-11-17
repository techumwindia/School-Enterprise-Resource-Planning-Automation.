from django import forms
from django.shortcuts import get_object_or_404, render

from accounts.crud import make_crud
from accounts.models import Role
from accounts.permissions import role_required

from .models import SalaryPayment, Staff


class StaffForm(forms.ModelForm):
    class Meta:
        model = Staff
        exclude = []
        widgets = {"subjects": forms.CheckboxSelectMultiple, "address": forms.Textarea(attrs={"rows": 2})}


StaffViews = make_crud(
    Staff, title="Staff", url_prefix="staff:staff", form_class=StaffForm,
    columns=(("Emp. ID", "employee_id"), ("Name", "name"), ("Designation", "designation"),
             ("Category", "category"), ("Phone", "phone"), ("Active", "is_active")),
    search_fields=("employee_id", "name", "designation", "phone"),
    list_filters=(("category", "category", lambda: Staff.CATEGORY, "Category"),),
)

SalaryViews = make_crud(
    SalaryPayment, title="Salary Payments", url_prefix="staff:salary",
    fields=["staff", "month", "basic", "allowances", "deductions", "paid_on", "remarks"],
    columns=(("Staff", "staff.name"), ("Month", "month"), ("Basic", "basic"), ("Allowances", "allowances"),
             ("Deductions", "deductions"), ("Net pay", "net_pay"), ("Paid on", "paid_on")),
    search_fields=("staff__name", "staff__employee_id"), select_related=("staff",),
    roles=(Role.ADMIN, Role.ACCOUNTANT),
    extra_actions=(("Payslip", "staff:payslip", "bi-printer"),),
)


@role_required(Role.ADMIN, Role.ACCOUNTANT)
def payslip(request, pk):
    p = get_object_or_404(SalaryPayment.objects.select_related("staff"), pk=pk)
    return render(request, "staff/payslip.html", {"p": p})

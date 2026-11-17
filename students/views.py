import csv

from django import forms
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from academics.models import ClassRoom
from accounts.crud import make_crud
from accounts.models import Role, user_role
from accounts.permissions import STAFF_ROLES, role_required
from attendance.models import attendance_percent
from exams.models import Exam
from fees.models import fee_ledger

from .models import Student


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        exclude = []
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}


def _class_choices():
    return [(c.pk, str(c)) for c in ClassRoom.objects.all()]


StudentViews = make_crud(
    Student, title="Students", url_prefix="students:student", form_class=StudentForm,
    columns=(("Adm. No", "admission_no"), ("Name", "full_name"), ("Class", "classroom"), ("Roll", "roll_no"),
             ("Gender", "gender"), ("Parent phone", "guardian_phone"), ("Active", "is_active")),
    search_fields=("admission_no", "first_name", "last_name", "guardian_phone", "father_name", "emis_no"),
    list_filters=(("classroom", "classroom_id", _class_choices, "Class"),
                  ("active", "is_active", lambda: [("1", "Active"), ("0", "Left")], "Status")),
    select_related=("classroom",), roles=(Role.ADMIN,),
    extra_actions=(("Profile", "students:detail", "bi-person-vcard"),),
)
# Teachers and accountants can browse the student list too (edit buttons are still admin-only)
StudentViews[0].allowed_roles = STAFF_ROLES


def can_view_student(user, student):
    role = user_role(user)
    if role in STAFF_ROLES:
        return True
    return (role == Role.STUDENT and student.user_id == user.id) or \
           (role == Role.PARENT and student.parent_user_id == user.id)


@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related("classroom"), pk=pk)
    if not can_view_student(request.user, student):
        raise PermissionDenied
    role = user_role(request.user)
    exams = Exam.objects.filter(marks__student=student).distinct()
    if role not in STAFF_ROLES:
        exams = exams.filter(is_published=True)
    att = student.attendance.all()
    return render(request, "students/detail.html", {
        "s": student,
        "attendance_pct": attendance_percent(att),
        "recent_attendance": att[:30],
        "ledger": fee_ledger(student),
        "payments": student.payments.select_related("fee__fee_type")[:20],
        "exams": exams,
    })


@role_required(Role.ADMIN, Role.TEACHER, Role.ACCOUNTANT)
def export_csv(request):
    qs = Student.objects.select_related("classroom").filter(is_active=True)
    if request.GET.get("classroom"):
        qs = qs.filter(classroom_id=request.GET["classroom"])
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="students.csv"'
    w = csv.writer(resp)
    w.writerow(["Admission No", "EMIS No", "Name", "Class", "Roll", "Gender", "DOB", "Father", "Mother",
                "Phone", "Email", "Address", "Bus"])
    for s in qs:
        w.writerow([s.admission_no, s.emis_no, s.full_name, s.classroom, s.roll_no, s.get_gender_display(),
                    s.date_of_birth, s.father_name, s.mother_name, s.guardian_phone, s.guardian_email,
                    s.address, "Yes" if s.uses_transport else "No"])
    return resp

import csv

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from academics.models import ClassRoom
from accounts.crud import make_crud
from accounts.models import Role, user_role
from accounts.permissions import STAFF_ROLES, role_required
from attendance.models import attendance_percent
from exams.models import Exam
from fees.models import fee_ledger

from .logins import ensure_logins, generate_password
from .models import Student


class StudentForm(forms.ModelForm):
    """Student details plus one login shared by the student and the parent."""
    login_username = forms.CharField(label="Username", required=False, max_length=150,
                                     validators=[UnicodeUsernameValidator()],
                                     help_text="Used by both the student and the parent.")
    login_password = forms.CharField(label="Password", required=False, max_length=128,
                                     help_text="Type a new password to set or change it.")

    class Meta:
        model = Student
        exclude = ["user", "parent_user"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login_username"].section = "Login (student & parent)"
        s = self.instance
        if not s.pk:  # new admission: blank fields are generated automatically
            self.fields["login_username"].help_text = "Leave blank to use the admission number."
            self.fields["login_password"].help_text = "Leave blank to generate a password."
        elif s.user:
            self.fields["login_username"].initial = s.user.username
            self.fields["login_password"].initial = s.user.profile.issued_password
        else:
            self.fields["login_username"].help_text = "No login yet. Enter a username, or leave blank."

    def clean(self):
        data = super().clean()
        username = data.get("login_username", "").strip()
        password = data.get("login_password", "")
        current = self.instance.user if self.instance.pk else None
        if username and User.objects.filter(username__iexact=username).exclude(
                pk=getattr(current, "pk", None)).exists():
            self.add_error("login_username", "This username is already used by someone else.")
        if password and len(password) < 4:
            self.add_error("login_password", "Use at least 4 characters.")
        return data

    def save(self, commit=True):
        is_new = not self.instance.pk
        current = self.instance.user if self.instance.pk else None
        student = super().save(commit=False)
        username = self.cleaned_data.get("login_username", "").strip()
        password = self.cleaned_data.get("login_password", "")

        if username:
            user = current or User(first_name=student.first_name[:150], last_name=student.last_name[:150])
            user.username = username
            if not user.pk:
                password = password or generate_password()
                user.set_password(password)
            elif password and password != user.profile.issued_password:
                user.set_password(password)
            user.save()
            profile = user.profile
            profile.role = Role.STUDENT
            if password:
                profile.issued_password = password
            profile.save()
            student.user = user
        elif not is_new:
            student.user = None  # login removed from this student (the account itself is kept)

        if commit:
            student.save()
            self.save_m2m()
            if is_new and not student.user_id:
                ensure_logins(student)  # username left blank on a new admission -> generate it
        return student


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
    sort_map={"full_name": ("first_name", "last_name"),
              "classroom": ("classroom__order", "classroom__section", "roll_no")},
    extra_actions=(("Profile", "students:detail", "bi-person-vcard"),),
)
# Teachers and accountants can browse the student list too (edit buttons are still admin-only)
StudentViews[0].allowed_roles = STAFF_ROLES
StudentViews[0].header_actions = (
    ("Create missing logins", "students:generate_logins", "bi-key",
     "Create a username and password for every active student that doesn't have one yet?"),
)


def _after_admission(self):
    messages.success(self.request, f"Admission saved for {self.object.full_name}. "
                                   "The login for the student and parent is shown below.")
    return reverse("students:detail", args=[self.object.pk])


StudentViews[1].get_success_url = _after_admission
StudentViews[1].save_message = False


def can_view_student(user, student):
    role = user_role(user)
    if role in STAFF_ROLES:
        return True
    return (role == Role.STUDENT and student.user_id == user.id) or \
           (role == Role.PARENT and student.parent_user_id == user.id)


@login_required
def student_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related("classroom", "user__profile"), pk=pk)
    if not can_view_student(request.user, student):
        raise PermissionDenied
    role = user_role(request.user)
    exams = Exam.objects.filter(marks__student=student).distinct()
    if role not in STAFF_ROLES:
        exams = exams.filter(is_published=True)
    att = student.attendance.all()
    return render(request, "students/detail.html", {
        "s": student,
        "login": student.user,
        "attendance_pct": attendance_percent(att),
        "recent_attendance": att[:30],
        "ledger": fee_ledger(student),
        "payments": student.payments.select_related("fee__fee_type")[:20],
        "exams": exams,
    })


@role_required(Role.ADMIN)
def generate_logins(request):
    """POST: create missing logins for one student (?student=pk) or for all active students."""
    if request.method != "POST":
        return redirect("students:student_list")
    pk = request.POST.get("student")
    qs = Student.objects.filter(pk=pk) if pk else Student.objects.filter(is_active=True)
    qs = qs.filter(user__isnull=True).order_by("pk")
    batch_size = 100  # password hashing is deliberately slow; keep each click well under the server timeout
    made = 0
    for s in qs[:batch_size]:
        made += bool(ensure_logins(s))
    if pk:
        messages.success(request, "Login created." if made else "This student already has a login.")
        return redirect("students:detail", pk=pk)
    remaining = qs.count()
    if remaining:
        messages.warning(request, f"Created {made} logins. {remaining} students still need one — click "
                                  "“Create missing logins” again to continue.")
    else:
        messages.success(request, f"Created {made} logins. Every student now has a login "
                                  "(shared by student and parent). Open a profile to see it.")
    return redirect("students:student_list")


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

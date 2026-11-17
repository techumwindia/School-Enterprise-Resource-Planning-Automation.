import csv

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
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
    """Student details plus the student's and parent's login (username + password)."""
    student_username = forms.CharField(required=False, max_length=150, validators=[UnicodeUsernameValidator()],
                                       help_text="Leave blank if the student doesn't need a login.")
    student_password = forms.CharField(required=False, max_length=128,
                                       help_text="Type a new password to set or change it.")
    parent_username = forms.CharField(required=False, max_length=150, validators=[UnicodeUsernameValidator()],
                                      help_text="Use the same parent username for brothers/sisters.")
    parent_password = forms.CharField(required=False, max_length=128,
                                      help_text="Type a new password to set or change it.")

    class Meta:
        model = Student
        exclude = ["user", "parent_user"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student_username"].section = "Login details"
        s = self.instance
        if not s.pk:  # new admission: blank fields are generated automatically
            self.fields["student_username"].help_text = "Leave blank to use the admission number."
            self.fields["parent_username"].help_text = ("Leave blank to use the parent's phone number "
                                                        "(links brothers/sisters automatically).")
            self.fields["student_password"].help_text = self.fields["parent_password"].help_text = \
                "Leave blank to generate a password."
        for prefix, user in (("student", s.user if s.pk else None), ("parent", s.parent_user if s.pk else None)):
            if user:
                self.fields[f"{prefix}_username"].initial = user.username
                self.fields[f"{prefix}_password"].initial = user.profile.issued_password

    def _check(self, prefix, current, role):
        username = self.cleaned_data.get(f"{prefix}_username", "").strip()
        password = self.cleaned_data.get(f"{prefix}_password", "")
        if not username:
            return
        other = User.objects.filter(username__iexact=username).exclude(pk=getattr(current, "pk", None)).first()
        if other:
            if role == Role.PARENT and user_role(other) == Role.PARENT:
                return  # existing parent login (sibling) – just link it
            self.add_error(f"{prefix}_username", "This username is already used by someone else.")
            return
        if password and len(password) < 4:
            self.add_error(f"{prefix}_password", "Use at least 4 characters.")

    def clean(self):
        data = super().clean()
        su = data.get("student_username", "").strip().lower()
        pu = data.get("parent_username", "").strip().lower()
        if su and su == pu:
            self.add_error("parent_username", "Student and parent need different usernames.")
        s = self.instance
        self._check("student", s.user if s.pk else None, Role.STUDENT)
        self._check("parent", s.parent_user if s.pk else None, Role.PARENT)
        return data

    def _login(self, prefix, current, role, first, last):
        """Create, rename, re-link or update the login for this student or parent."""
        username = self.cleaned_data.get(f"{prefix}_username", "").strip()
        password = self.cleaned_data.get(f"{prefix}_password", "")
        if not username:
            return None  # login unlinked from this student (the account itself is kept)

        same_name = User.objects.filter(username__iexact=username).first()
        if same_name:
            user = same_name  # this student's own login, or a sibling's parent login
        elif current and not (role == Role.PARENT and current.children.exclude(pk=self.instance.pk).exists()):
            user = current    # rename this login
        else:
            user = User(first_name=first, last_name=last)  # new login (or this child gets its own parent login)
        user.username = username

        if not user.pk:
            password = password or generate_password()
            user.set_password(password)
        elif password and password != user.profile.issued_password:
            user.set_password(password)
        user.save()
        profile = user.profile
        profile.role = role
        if password:
            profile.issued_password = password
        profile.save()
        return user

    def save(self, commit=True):
        s = self.instance
        self._is_new = not s.pk
        before_student = s.user if s.pk else None
        before_parent = s.parent_user if s.pk else None
        student = super().save(commit=False)
        student.user = self._login("student", before_student, Role.STUDENT, student.first_name, student.last_name)
        parent_name = student.father_name or student.mother_name or f"Parent of {student.first_name}"
        student.parent_user = self._login("parent", before_parent, Role.PARENT, parent_name, "")
        if commit:
            student.save()
            self.save_m2m()
            if self._is_new:
                ensure_logins(student)  # fill in any login left blank on a new admission
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
     "Create usernames and passwords for every active student and parent that doesn't have one yet?"),
)


def _after_admission(self):
    messages.success(self.request, f"Admission saved for {self.object.full_name}. "
                                   "Student and parent logins are shown below.")
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
    student = get_object_or_404(Student.objects.select_related(
        "classroom", "user__profile", "parent_user__profile"), pk=pk)
    if not can_view_student(request.user, student):
        raise PermissionDenied
    role = user_role(request.user)
    exams = Exam.objects.filter(marks__student=student).distinct()
    if role not in STAFF_ROLES:
        exams = exams.filter(is_published=True)
    att = student.attendance.all()
    return render(request, "students/detail.html", {
        "s": student,
        "logins": [("Student login", student.user), ("Parent login", student.parent_user)],
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
    qs = qs.filter(Q(user__isnull=True) | Q(parent_user__isnull=True)).order_by("pk")
    batch_size = 50  # password hashing is deliberately slow; keep each click well under the server timeout
    students = parents = 0
    for s in qs[:batch_size]:
        made = ensure_logins(s)
        students += "student" in made
        parents += "parent" in made
    if pk:
        messages.success(request, "Logins created." if students or parents else "This student already has logins.")
        return redirect("students:detail", pk=pk)
    remaining = qs.count()
    msg = (f"Created {students} student logins and {parents} parent logins "
           "(brothers/sisters with the same phone share one parent login). ")
    if remaining:
        messages.warning(request, msg + f"{remaining} students still need logins — click "
                                        "“Create missing logins” again to continue.")
    else:
        messages.success(request, msg + "All students now have logins. "
                                        "Open a student's profile to see the username and password.")
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

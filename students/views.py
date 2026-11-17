import calendar
import csv
from datetime import date, timedelta

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from academics.models import AcademicYear, ClassRoom
from accounts.crud import make_crud, style_form
from accounts.models import Role, user_role
from accounts.permissions import STAFF_ROLES, role_required
from attendance.models import Attendance, attendance_percent
from exams.models import Exam, Mark, grade_for
from fees.models import fee_ledger

from .logins import ensure_logins, generate_password, student_username
from .models import Student


class StudentForm(forms.ModelForm):
    """Student details. The login is created automatically on admission and managed from the profile."""

    class Meta:
        model = Student
        exclude = ["user", "parent_user"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2})}

    def save(self, commit=True):
        is_new = not self.instance.pk
        student = super().save(commit=commit)
        if commit and is_new:
            ensure_logins(student)  # username = admission no, random password
        return student


class LoginForm(forms.Form):
    """Username / password for the login shared by the student and the parent."""
    username = forms.CharField(max_length=150, validators=[UnicodeUsernameValidator()],
                               help_text="Used by both the student and the parent.")
    password = forms.CharField(required=False, max_length=128,
                               help_text="Leave as it is to keep the current password.")

    def __init__(self, *args, student=None, **kwargs):
        self.student = student
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.student.user_id).exists():
            raise forms.ValidationError("This username is already used by someone else.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if password and len(password) < 4:
            raise forms.ValidationError("Use at least 4 characters.")
        return password

    def save(self):
        student = self.student
        user = student.user or User(first_name=student.first_name[:150], last_name=student.last_name[:150])
        password = self.cleaned_data["password"]
        user.username = self.cleaned_data["username"]
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
        if student.user_id != user.pk:
            student.user = user
            student.save(update_fields=["user"])
        return user


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
                                   "The login for the student and parent is shown in the Login card.")
    return reverse("students:detail", args=[self.object.pk])


StudentViews[1].get_success_url = _after_admission
StudentViews[1].save_message = False


def can_view_student(user, student):
    role = user_role(user)
    if role in STAFF_ROLES:
        return True
    return (role == Role.STUDENT and student.user_id == user.id) or \
           (role == Role.PARENT and student.parent_user_id == user.id)


def _student_for(request, pk):
    student = get_object_or_404(Student.objects.select_related("classroom", "user__profile"), pk=pk)
    if not can_view_student(request.user, student):
        raise PermissionDenied
    return student


def _exams_for(request, student):
    """Exams this student has marks in, newest first (students/parents: published only)."""
    exams = (Exam.objects.filter(marks__student=student).distinct().select_related("academic_year")
             .order_by("-academic_year__start_date", "-start_date", "-id"))
    if user_role(request.user) not in STAFF_ROLES:
        exams = exams.filter(is_published=True)
    return exams


def exam_block(exam, student):
    """Marks, total, %, grade, rank and result of one student in one exam."""
    from exams.views import class_results  # local import: exams.views imports this module
    marks = Mark.objects.filter(exam=exam, student=student).select_related("subject").order_by("subject__name")
    total = sum((m.marks or 0) for m in marks)
    maximum = exam.max_marks * len(marks)
    pct = round(float(total) * 100 / maximum, 1) if maximum else None
    failed = any(m.absent or (m.marks is not None and m.marks < exam.pass_marks) for m in marks)
    rank = None
    if student.classroom and not failed:
        _subs, rows = class_results(exam, student.classroom)
        rank = next((r.get("rank") for r in rows if r["s"].pk == student.pk), None)
    lines = [{"m": m, "pct": round(float(m.marks) * 100 / exam.max_marks, 1) if m.marks is not None else None,
              "grade": grade_for(float(m.marks) * 100 / exam.max_marks if m.marks is not None else None),
              "pass": not m.absent and m.marks is not None and m.marks >= exam.pass_marks} for m in marks]
    return {"exam": exam, "lines": lines, "total": total, "maximum": maximum, "pct": pct,
            "grade": grade_for(pct), "result": "FAIL" if failed else "PASS", "rank": rank}


def year_of(day, years):
    """The AcademicYear a date falls in (years: list of AcademicYear), or None."""
    return next((y for y in years if y.start_date <= day <= y.end_date), None)


@login_required
def student_detail(request, pk):
    student = _student_for(request, pk)
    since = timezone.localdate() - timedelta(days=29)
    last30 = student.attendance.filter(date__gte=since)
    exams = _exams_for(request, student)
    return render(request, "students/detail.html", {
        "s": student,
        "login": student.user,
        "attendance_pct": attendance_percent(last30),
        "recent_attendance": last30.order_by("-date"),
        "last30_counts": {code: last30.filter(status=code).count() for code, _ in Attendance.STATUS},
        "ledger": fee_ledger(student),
        "exam_count": exams.count(),
        "latest": exam_block(exams[0], student) if exams else None,
    })


@login_required
def fees_detail(request, pk):
    """Popup: fee status for every fee item plus all payments with receipts."""
    student = _student_for(request, pk)
    ledger = fee_ledger(student)
    today = timezone.localdate()
    for r in ledger["rows"]:
        if r["balance"] <= 0:
            r["status"], r["badge"] = "Paid", "success"
        elif r["overdue"]:
            r["status"], r["badge"] = "Overdue", "danger"
        elif r["paid"] > 0:
            r["status"], r["badge"] = "Partly paid", "warning"
        elif r["fee"].due_date and r["fee"].due_date >= today:
            r["status"], r["badge"] = "Not yet due", "secondary"
        else:
            r["status"], r["badge"] = "Due", "warning"
    payments = student.payments.select_related("fee__fee_type", "fee__academic_year", "collected_by")
    return render(request, "students/popup_fees.html", {
        "s": student, "ledger": ledger, "payments": payments,
        "paid_total": sum(p.amount for p in payments), "concession_total": sum(p.concession for p in payments),
    })


def _month_block(y, m, records):
    cal = calendar.Calendar(firstweekday=0).monthdatescalendar(y, m)
    weeks = [[{"date": d, "in_month": d.month == m, "rec": records.get(d)} for d in wk] for wk in cal]
    mine = [r for d, r in records.items() if d.year == y and d.month == m]
    counts = {code: sum(1 for r in mine if r.status == code) for code, _ in Attendance.STATUS}
    total = len(mine)
    pct = round((counts["P"] + counts["H"] * 0.5) * 100 / total, 1) if total else None
    return {"label": date(y, m, 1).strftime("%B %Y"), "weeks": weeks, "counts": counts, "total": total, "pct": pct}


@login_required
def attendance_detail(request, pk):
    """Popup: attendance grouped by academic year — totals and a month-by-month calendar."""
    student = _student_for(request, pk)
    years = list(AcademicYear.objects.order_by("-start_date"))
    groups = {}  # year (or None) -> {date: record}
    for a in student.attendance.order_by("date"):
        groups.setdefault(year_of(a.date, years), {})[a.date] = a

    blocks = []
    for year in sorted(groups, key=lambda y: (y is not None, y.start_date if y else date.min), reverse=True):
        recs = groups[year]
        first, last = min(recs), max(recs)
        months = []
        y, m = first.year, first.month
        while (y, m) <= (last.year, last.month):
            months.append(_month_block(y, m, recs))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        months.reverse()  # latest month first
        counts = {code: sum(1 for r in recs.values() if r.status == code) for code, _ in Attendance.STATUS}
        total = len(recs)
        blocks.append({
            "key": f"y{year.pk}" if year else "other",
            "label": year.name if year else "Other dates",
            "current": bool(year and year.is_current),
            "months": months, "counts": counts, "total": total,
            "pct": round((counts["P"] + counts["H"] * 0.5) * 100 / total, 1) if total else None,
        })
    return render(request, "students/popup_attendance.html", {
        "s": student, "blocks": blocks, "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    })


@login_required
def results_detail(request, pk):
    """Popup: every exam result grouped by academic year."""
    student = _student_for(request, pk)
    by_year = {}
    for exam in _exams_for(request, student):
        by_year.setdefault(exam.academic_year, []).append(exam_block(exam, student))
    for blocks in by_year.values():  # within a year: in the order the exams were held
        blocks.reverse()
    years = [{"key": f"r{y.pk}", "label": y.name, "current": y.is_current, "blocks": blocks,
              "avg": round(sum(b["pct"] for b in blocks if b["pct"] is not None) /
                           max(1, sum(1 for b in blocks if b["pct"] is not None)), 1)}
             for y, blocks in by_year.items()]  # already newest year first
    return render(request, "students/popup_results.html", {"s": student, "years": years})


@role_required(Role.ADMIN)
def login_edit(request, pk):
    """Popup form (admin): change the username / password of the student's login."""
    student = get_object_or_404(Student.objects.select_related("user__profile"), pk=pk)
    initial = {"username": student.user.username, "password": student.user.profile.issued_password} \
        if student.user else {"username": student_username(student), "password": generate_password()}
    if request.method == "POST":
        form = LoginForm(request.POST, student=student)
        if form.is_valid():
            form.save()
            messages.success(request, "Login updated.")
            return HttpResponse(status=204)  # popup closes and the profile reloads
    else:
        form = LoginForm(initial=initial, student=student)
    style_form(form)
    return render(request, "students/popup_login.html", {"s": student, "form": form,
                                                          "suggested": generate_password()})


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

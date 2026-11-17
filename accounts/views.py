from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from academics.models import AcademicYear, ClassRoom, TimetableEntry
from attendance.models import Attendance, attendance_percent
from exams.models import Exam
from fees.models import FeePayment, FeeStructure, fee_ledger
from notices.models import Event, notices_for
from staff.models import Staff
from students.models import Student

from .crud import make_crud, style_form
from .forms import UserForm
from .models import Role, user_role


@login_required
def dashboard(request):
    role = user_role(request.user)
    today = timezone.localdate()
    ctx = {
        "role": role,
        "today": today,
        "notices": notices_for(role)[:5],
        "events": Event.objects.filter(date__gte=today)[:5],
    }

    if role in (Role.ADMIN, Role.ACCOUNTANT, Role.TEACHER):
        students = Student.objects.filter(is_active=True)
        todays = Attendance.objects.filter(date=today)
        month_start = today.replace(day=1)
        ctx.update(
            student_count=students.count(),
            staff_count=Staff.objects.filter(is_active=True).count(),
            class_count=ClassRoom.objects.count(),
            boys=students.filter(gender="M").count(),
            girls=students.filter(gender="F").count(),
            attendance_marked=todays.count(),
            attendance_today=attendance_percent(todays),
            absent_today=todays.filter(status=Attendance.ABSENT).select_related("student", "student__classroom")[:10],
            fees_today=FeePayment.objects.filter(paid_on=today).aggregate(s=Sum("amount"))["s"] or 0,
            fees_month=FeePayment.objects.filter(paid_on__gte=month_start).aggregate(s=Sum("amount"))["s"] or 0,
            recent_payments=FeePayment.objects.select_related("student", "fee__fee_type")[:6],
            class_strength=ClassRoom.objects.annotate(
                n=Count("students", filter=Q(students__is_active=True))).order_by("order", "section"),
        )
        # Fee collection trend: last 7 days
        trend = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            trend.append({"day": d, "amount": FeePayment.objects.filter(paid_on=d).aggregate(s=Sum("amount"))["s"] or 0})
        peak = max((t["amount"] for t in trend), default=0) or 1
        for t in trend:
            t["pct"] = int(t["amount"] * 100 / peak)
        ctx["trend"] = trend

        if role == Role.TEACHER:
            staff = getattr(request.user, "staff", None)
            ctx["my_classes"] = ClassRoom.objects.filter(class_teacher=staff) if staff else []
            ctx["my_periods"] = (TimetableEntry.objects.filter(teacher=staff, day=today.isoweekday())
                                 .select_related("classroom", "subject").order_by("period")) if staff else []

    else:  # student / parent
        if role == Role.STUDENT:
            kids = Student.objects.filter(user=request.user)
        else:
            kids = Student.objects.filter(parent_user=request.user)
        children = []
        for s in kids.select_related("classroom"):
            att = s.attendance.all()
            children.append({
                "student": s,
                "attendance": attendance_percent(att),
                "ledger": fee_ledger(s),
                "exams": Exam.objects.filter(is_published=True, marks__student=s).distinct(),
                "today_tt": TimetableEntry.objects.filter(classroom=s.classroom, day=today.isoweekday())
                .select_related("subject").order_by("period"),
            })
        ctx["children"] = children

    return render(request, "accounts/dashboard.html", ctx)


def _user_choices():
    return Role.choices


UserViews = make_crud(
    User, title="User Accounts", url_prefix="accounts:user", form_class=UserForm,
    columns=(("Username", "username"), ("Name", "get_full_name"), ("Role", "profile.role"),
             ("Active", "is_active"), ("Last login", "last_login")),
    search_fields=("username", "first_name", "last_name", "email"),
    list_filters=(("role", "profile__role", _user_choices, "Role"),),
    ordering=("username",), select_related=("profile",),
    sort_map={"get_full_name": ("first_name", "last_name")},
)


class PasswordChange(auth_views.PasswordChangeView):
    template_name = "crud/form.html"
    success_url = "/"
    extra_context = {"title": "Change Password"}

    def get_form(self, form_class=None):
        return style_form(super().get_form(form_class))

    def form_valid(self, form):
        messages.success(self.request, "Password changed.")
        return super().form_valid(form)

import calendar
from datetime import date

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from academics.models import ClassRoom
from accounts.models import Role
from accounts.permissions import STAFF_ROLES, role_required

from .models import Attendance, attendance_percent


def _pick_class(request):
    classes = ClassRoom.objects.all()
    staff = getattr(request.user, "staff", None)
    default = classes.filter(class_teacher=staff).first() if staff else None
    selected = classes.filter(pk=request.GET.get("classroom") or request.POST.get("classroom")).first()
    return classes, selected or default or classes.first()


@role_required(Role.ADMIN, Role.TEACHER)
def mark(request):
    classes, classroom = _pick_class(request)
    day = parse_date(request.GET.get("date") or request.POST.get("date") or "") or timezone.localdate()
    students = classroom.students.filter(is_active=True) if classroom else []

    if request.method == "POST" and classroom:
        if day > timezone.localdate():
            messages.error(request, "Attendance cannot be marked for a future date.")
        else:
            saved = 0
            for s in students:
                status = request.POST.get(f"s_{s.pk}")
                if status in dict(Attendance.STATUS):
                    Attendance.objects.update_or_create(
                        student=s, date=day, defaults={"status": status, "marked_by": request.user})
                    saved += 1
            messages.success(request, f"Attendance saved for {saved} students of {classroom} on {day:%d %b %Y}.")
            return redirect(f"{request.path}?classroom={classroom.pk}&date={day.isoformat()}")

    existing = dict(Attendance.objects.filter(student__in=students, date=day).values_list("student_id", "status"))
    rows = [{"s": s, "status": existing.get(s.pk, Attendance.PRESENT)} for s in students]
    return render(request, "attendance/mark.html", {
        "classes": classes, "classroom": classroom, "day": day, "rows": rows,
        "statuses": Attendance.STATUS, "already_marked": bool(existing),
        "summary": {k: sum(1 for r in rows if r["status"] == k) for k, _ in Attendance.STATUS},
    })


@role_required(*STAFF_ROLES)
def report(request):
    classes, classroom = _pick_class(request)
    today = timezone.localdate()
    try:
        year, month = map(int, (request.GET.get("month") or f"{today:%Y-%m}").split("-"))
    except ValueError:
        year, month = today.year, today.month
    ndays = calendar.monthrange(year, month)[1]
    days = [date(year, month, d) for d in range(1, ndays + 1)]

    rows = []
    if classroom:
        records = Attendance.objects.filter(student__classroom=classroom, date__year=year, date__month=month)
        grid = {(a.student_id, a.date.day): a.status for a in records}
        for s in classroom.students.filter(is_active=True):
            mine = records.filter(student=s)
            rows.append({"s": s, "cells": [grid.get((s.pk, d.day), "") for d in days],
                         "present": mine.filter(status="P").count(), "absent": mine.filter(status="A").count(),
                         "pct": attendance_percent(mine)})
    return render(request, "attendance/report.html", {
        "classes": classes, "classroom": classroom, "days": days, "rows": rows,
        "month_value": f"{year}-{month:02d}", "month_label": date(year, month, 1).strftime("%B %Y"),
    })

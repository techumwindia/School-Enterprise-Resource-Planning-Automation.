from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import ClassRoom, Subject
from accounts.crud import make_crud
from accounts.models import Role, user_role
from accounts.permissions import STAFF_ROLES, role_required
from students.models import Student
from students.views import can_view_student

from .models import Exam, Mark, grade_for

ExamViews = make_crud(
    Exam, title="Exams", url_prefix="exams:exam",
    fields=["name", "academic_year", "start_date", "max_marks", "pass_marks", "is_published"],
    columns=(("Exam", "name"), ("Year", "academic_year"), ("Starts", "start_date"), ("Max", "max_marks"),
             ("Pass", "pass_marks"), ("Published", "is_published")),
    select_related=("academic_year",),
)


def _selection(request):
    exams = Exam.objects.select_related("academic_year")
    classes = ClassRoom.objects.all()
    src = request.POST if request.method == "POST" else request.GET
    exam = exams.filter(pk=src.get("exam")).first() or exams.first()
    classroom = classes.filter(pk=src.get("classroom")).first() or classes.first()
    return exams, classes, exam, classroom


@role_required(Role.ADMIN, Role.TEACHER)
def entry(request):
    exams, classes, exam, classroom = _selection(request)
    subjects = classroom.subjects.all() if classroom else Subject.objects.none()
    if classroom and not subjects.exists():
        subjects = Subject.objects.all()
    src = request.POST if request.method == "POST" else request.GET
    subject = subjects.filter(pk=src.get("subject")).first() or subjects.first()
    students = classroom.students.filter(is_active=True) if classroom else Student.objects.none()

    if request.method == "POST" and exam and subject:
        errors = 0
        for s in students:
            raw = request.POST.get(f"m_{s.pk}", "").strip()
            absent = request.POST.get(f"ab_{s.pk}") == "on"
            if not raw and not absent:
                Mark.objects.filter(exam=exam, student=s, subject=subject).delete()
                continue
            try:
                value = None if absent else Decimal(raw)
            except InvalidOperation:
                errors += 1
                continue
            if value is not None and not (0 <= value <= exam.max_marks):
                errors += 1
                continue
            Mark.objects.update_or_create(exam=exam, student=s, subject=subject,
                                          defaults={"marks": value, "absent": absent})
        if errors:
            messages.warning(request, f"{errors} entries were skipped (must be between 0 and {exam.max_marks}).")
        else:
            messages.success(request, f"{subject} marks saved for {classroom}.")
        return redirect(f"{request.path}?exam={exam.pk}&classroom={classroom.pk}&subject={subject.pk}")

    existing = {m.student_id: m for m in Mark.objects.filter(exam=exam, subject=subject, student__in=students)} \
        if exam and subject else {}
    rows = [{"s": s, "m": existing.get(s.pk)} for s in students]
    return render(request, "exams/entry.html", {
        "exams": exams, "classes": classes, "subjects": subjects,
        "exam": exam, "classroom": classroom, "subject": subject, "rows": rows,
    })


def class_results(exam, classroom):
    subjects = list(Subject.objects.filter(mark__exam=exam, mark__student__classroom=classroom).distinct())
    marks = Mark.objects.filter(exam=exam, student__classroom=classroom)
    grid = {(m.student_id, m.subject_id): m for m in marks}
    rows = []
    for s in classroom.students.filter(is_active=True):
        cells, total, failed = [], Decimal(0), False
        for sub in subjects:
            m = grid.get((s.pk, sub.pk))
            cells.append(m)
            if m and m.marks is not None:
                total += m.marks
            if m and (m.absent or (m.marks is not None and m.marks < exam.pass_marks)):
                failed = True
        maximum = exam.max_marks * len(subjects)
        pct = round(float(total) * 100 / maximum, 1) if maximum else None
        rows.append({"s": s, "cells": cells, "total": total, "pct": pct, "grade": grade_for(pct),
                     "result": "FAIL" if failed else "PASS"})
    ranked = sorted([r for r in rows if r["result"] == "PASS"], key=lambda r: -r["total"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return subjects, rows


@role_required(Role.ADMIN, Role.TEACHER)
def results(request):
    exams, classes, exam, classroom = _selection(request)
    subjects, rows = class_results(exam, classroom) if exam and classroom else ([], [])
    passed = sum(1 for r in rows if r["result"] == "PASS")
    return render(request, "exams/results.html", {
        "exams": exams, "classes": classes, "exam": exam, "classroom": classroom,
        "subjects": subjects, "rows": rows, "passed": passed,
        "pass_pct": round(passed * 100 / len(rows), 1) if rows else None,
    })


@login_required
def report_card(request, exam_pk, student_pk):
    exam = get_object_or_404(Exam, pk=exam_pk)
    student = get_object_or_404(Student.objects.select_related("classroom"), pk=student_pk)
    if not can_view_student(request.user, student):
        raise PermissionDenied
    if user_role(request.user) not in STAFF_ROLES and not exam.is_published:
        raise PermissionDenied
    marks = Mark.objects.filter(exam=exam, student=student).select_related("subject").order_by("subject__name")
    total = sum((m.marks or 0) for m in marks)
    maximum = exam.max_marks * len(marks)
    pct = round(float(total) * 100 / maximum, 1) if maximum else None
    failed = any(m.absent or (m.marks is not None and m.marks < exam.pass_marks) for m in marks)
    rank = None
    if student.classroom and not failed:
        _subs, rows = class_results(exam, student.classroom)
        rank = next((r.get("rank") for r in rows if r["s"].pk == student.pk), None)
    lines = [{"m": m, "grade": grade_for(float(m.marks) * 100 / exam.max_marks if m.marks is not None else None),
              "pass": not m.absent and m.marks is not None and m.marks >= exam.pass_marks} for m in marks]
    return render(request, "exams/report_card.html", {
        "exam": exam, "s": student, "lines": lines, "total": total, "maximum": maximum, "pct": pct,
        "grade": grade_for(pct), "result": "FAIL" if failed else "PASS", "rank": rank,
        "attendance": student.attendance.all(),
    })

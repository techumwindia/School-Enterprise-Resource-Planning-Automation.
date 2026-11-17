from django import forms
from django.shortcuts import get_object_or_404, render

from accounts.crud import make_crud
from accounts.models import Role, user_role
from accounts.permissions import STAFF_ROLES, role_required

from .models import AcademicYear, ClassRoom, Subject, TimetableEntry

YearViews = make_crud(
    AcademicYear, title="Academic Years", url_prefix="academics:year",
    fields=["name", "start_date", "end_date", "is_current"],
    columns=(("Year", "name"), ("Start", "start_date"), ("End", "end_date"), ("Current", "is_current")),
)

SubjectViews = make_crud(
    Subject, title="Subjects", url_prefix="academics:subject", fields=["name", "code"],
    columns=(("Subject", "name"), ("Code", "code")), search_fields=("name", "code"),
)


class ClassRoomForm(forms.ModelForm):
    class Meta:
        model = ClassRoom
        fields = ["grade", "section", "order", "class_teacher", "room_no", "subjects"]
        widgets = {"subjects": forms.CheckboxSelectMultiple}


ClassViews = make_crud(
    ClassRoom, title="Classes", url_prefix="academics:class", form_class=ClassRoomForm,
    columns=(("Class", "__str__"), ("Class teacher", "class_teacher.name"), ("Room", "room_no"),
             ("Students", "student_count")),
    search_fields=("grade", "section"), select_related=("class_teacher",),
    extra_actions=(("View", "academics:class_detail", "bi-eye"),),
)


def _class_choices():
    return [(c.pk, str(c)) for c in ClassRoom.objects.all()]


TimetableViews = make_crud(
    TimetableEntry, title="Timetable Entries", url_prefix="academics:tt",
    fields=["classroom", "day", "period", "subject", "teacher"],
    columns=(("Class", "classroom"), ("Day", "day"), ("Period", "period"), ("Subject", "subject"),
             ("Teacher", "teacher.name")),
    list_filters=(("classroom", "classroom_id", _class_choices, "Class"),),
    select_related=("classroom", "subject", "teacher"),
)


def build_grid(classroom):
    entries = TimetableEntry.objects.filter(classroom=classroom).select_related("subject", "teacher")
    periods = sorted({e.period for e in entries}) or list(range(1, 9))
    by_key = {(e.day, e.period): e for e in entries}
    rows = [{"day": name, "cells": [by_key.get((d, p)) for p in periods]} for d, name in TimetableEntry.DAYS]
    return periods, rows


@role_required(*STAFF_ROLES)
def class_detail(request, pk):
    classroom = get_object_or_404(ClassRoom.objects.select_related("class_teacher"), pk=pk)
    periods, rows = build_grid(classroom)
    return render(request, "academics/class_detail.html", {
        "classroom": classroom,
        "students": classroom.students.filter(is_active=True),
        "periods": periods, "rows": rows,
    })


@role_required(*STAFF_ROLES)
def timetable(request):
    classes = ClassRoom.objects.all()
    selected = classes.filter(pk=request.GET.get("classroom")).first() or classes.first()
    periods, rows = build_grid(selected) if selected else ([], [])
    return render(request, "academics/timetable.html", {
        "classes": classes, "selected": selected, "periods": periods, "rows": rows,
        "can_edit": user_role(request.user) == Role.ADMIN,
    })


# Teachers and accountants can browse classes (edit buttons stay admin-only)
ClassViews[0].allowed_roles = STAFF_ROLES

"""Automatic login for each student — one login shared by the student and the parent.

Username = admission number in lowercase (A1121 -> a1121).
Password = 8 random characters without look-alikes (no 0/O, 1/l/i).
"""
import re
import secrets

from django.contrib.auth.models import User

from accounts.models import Role

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def generate_password(length=8):
    while True:
        pw = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw):
            return pw


def _clean(text):
    return re.sub(r"[^\w.@+-]", "", text or "").lower()


def _unique(base, exclude_pk=None):
    name, n = base, 2
    while User.objects.filter(username__iexact=name).exclude(pk=exclude_pk).exists():
        name, n = f"{base}-{n}", n + 1
    return name


def student_username(student):
    return _unique(_clean(student.admission_no) or f"student{student.pk or ''}")


def ensure_login(student, save=True):
    """Create the student's login if it has none. Returns True if one was created."""
    if student.user_id:
        return False
    password = generate_password()
    user = User(username=student_username(student), first_name=student.first_name[:150],
                last_name=student.last_name[:150])
    user.set_password(password)
    user.save()
    user.profile.role = Role.STUDENT
    user.profile.issued_password = password
    user.profile.save()
    student.user = user
    if save:
        student.save(update_fields=["user"])
    return True


ensure_logins = ensure_login  # old name

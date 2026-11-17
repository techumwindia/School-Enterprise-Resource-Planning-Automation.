"""Automatic usernames and passwords for students and parents.

Student username = admission number in lowercase (A1121 -> a1121).
Parent username  = parent's 10-digit phone number, so brothers/sisters with the
                   same phone share one parent login. Falls back to "p" + admission no.
Passwords        = 8 random characters without look-alikes (no 0/O, 1/l/i).
"""
import re
import secrets

from django.contrib.auth.models import User

from accounts.models import Role, user_role

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


def parent_login_for(student):
    """(username, existing parent user or None). Reuses a sibling's parent login with the same phone."""
    digits = re.sub(r"\D", "", student.guardian_phone or "")[-10:]
    if len(digits) == 10:
        existing = User.objects.filter(username=digits).first()
        if existing is None:
            return digits, None
        if user_role(existing) == Role.PARENT:
            return digits, existing
    return _unique("p" + (_clean(student.admission_no) or "parent")), None


def _create(username, password, role, first, last=""):
    user = User(username=username, first_name=first[:150], last_name=last[:150])
    user.set_password(password)
    user.save()
    user.profile.role = role
    user.profile.issued_password = password
    user.profile.save()
    return user


def ensure_logins(student, save=True):
    """Create whichever of the student / parent logins is missing. Returns a list of what was created."""
    created = []
    if not student.user_id:
        pw = generate_password()
        student.user = _create(student_username(student), pw, Role.STUDENT, student.first_name, student.last_name)
        created.append("student")
    if not student.parent_user_id:
        username, sibling_parent = parent_login_for(student)
        if sibling_parent:
            student.parent_user = sibling_parent
            created.append("parent (linked to sibling)")
        else:
            name = student.father_name or student.mother_name or f"Parent of {student.first_name}"
            student.parent_user = _create(username, generate_password(), Role.PARENT, name)
            created.append("parent")
    if created and save:
        student.save(update_fields=["user", "parent_user"])
    return created

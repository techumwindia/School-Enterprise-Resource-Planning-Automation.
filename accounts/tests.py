"""Smoke tests: every page renders for the right roles and is blocked for the others.
Run with:  python manage.py test
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from attendance.models import Attendance
from exams.models import Exam, Mark
from fees.models import FeePayment, fee_ledger
from staff.models import SalaryPayment
from students.models import Student

PASSWORDS = {"admin": "admin123", "teacher1": "teacher123", "accountant": "accounts123",
             "student1": "student123", "parent1": "parent123"}


class SmokeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def login(self, username):
        self.client.logout()
        self.assertTrue(self.client.login(username=username, password=PASSWORDS[username]))

    def urls(self):
        s = Student.objects.get(user__username="student1")
        other = Student.objects.exclude(pk=s.pk).first()
        p = FeePayment.objects.filter(student=s).first()
        exam = Exam.objects.get(name="Quarterly")
        sal = SalaryPayment.objects.first()
        return {
            "dashboard": reverse("accounts:dashboard"),
            "notices": reverse("notices:board"),
            "students": reverse("students:student_list"),
            "student_add": reverse("students:student_add"),
            "own_student": reverse("students:detail", args=[s.pk]),
            "other_student": reverse("students:detail", args=[other.pk]),
            "classes": reverse("academics:class_list"),
            "class_detail": reverse("academics:class_detail", args=[s.classroom_id]),
            "timetable": reverse("academics:timetable"),
            "tt_entries": reverse("academics:tt_list"),
            "subjects": reverse("academics:subject_list"),
            "years": reverse("academics:year_list"),
            "attendance": reverse("attendance:mark"),
            "attendance_report": reverse("attendance:report"),
            "marks": reverse("exams:entry"),
            "results": reverse("exams:results"),
            "exams": reverse("exams:exam_list"),
            "report_card": reverse("exams:report_card", args=[exam.pk, s.pk]),
            "collect": reverse("fees:collect") + f"?student={s.pk}",
            "payments": reverse("fees:payments"),
            "dues": reverse("fees:dues"),
            "receipt": reverse("fees:receipt", args=[p.pk]),
            "structure": reverse("fees:structure_list"),
            "fee_types": reverse("fees:type_list"),
            "staff": reverse("staff:staff_list"),
            "staff_add": reverse("staff:staff_add"),
            "salary": reverse("staff:salary_list"),
            "payslip": reverse("staff:payslip", args=[sal.pk]),
            "users": reverse("accounts:user_list"),
            "user_add": reverse("accounts:user_add"),
            "notices_manage": reverse("notices:notice_list"),
            "events": reverse("notices:event_list"),
            "export": reverse("students:export"),
            "password": reverse("accounts:password_change"),
        }

    ACCESS = {
        "admin": "all",
        "teacher1": {"dashboard", "notices", "students", "own_student", "other_student", "classes", "class_detail",
                     "timetable", "attendance", "attendance_report", "marks", "results", "report_card", "export",
                     "password", "receipt"},
        "accountant": {"dashboard", "notices", "students", "own_student", "other_student", "classes",
                       "class_detail", "timetable", "attendance_report", "report_card", "collect", "payments",
                       "dues", "receipt", "structure", "fee_types", "salary", "payslip", "export", "password"},
        "student1": {"dashboard", "notices", "own_student", "report_card", "receipt", "password"},
        "parent1": {"dashboard", "notices", "own_student", "report_card", "receipt", "password"},
    }

    def test_role_access(self):
        urls = self.urls()
        for user, allowed in self.ACCESS.items():
            self.login(user)
            for name, url in urls.items():
                resp = self.client.get(url)
                expected = 200 if allowed == "all" or name in allowed else 403
                self.assertEqual(resp.status_code, expected, f"{user} → {name} ({url})")

    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse("fees:dues"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp["Location"])

    def test_mark_attendance(self):
        self.login("teacher1")
        s = Student.objects.get(user__username="student1")
        day = timezone.localdate() - timedelta(days=60)
        data = {"classroom": s.classroom_id, "date": day.isoformat()}
        for st in s.classroom.students.all():
            data[f"s_{st.pk}"] = "A" if st.pk == s.pk else "P"
        self.client.post(reverse("attendance:mark"), data)
        self.assertEqual(Attendance.objects.get(student=s, date=day).status, "A")
        # future dates are rejected
        data["date"] = (timezone.localdate() + timedelta(days=3)).isoformat()
        self.client.post(reverse("attendance:mark"), data)
        self.assertFalse(Attendance.objects.filter(date=data["date"]).exists())

    def test_collect_fee_and_overpayment_guard(self):
        self.login("accountant")
        s = Student.objects.get(user__username="student1")
        row = next(r for r in fee_ledger(s)["rows"] if r["balance"] > 0)
        before = FeePayment.objects.count()
        self.client.post(reverse("fees:collect"), {"student": s.pk, "fee": row["fee"].pk,
                                                   "amount": str(row["balance"] + 1), "mode": "cash"})
        self.assertEqual(FeePayment.objects.count(), before)
        resp = self.client.post(reverse("fees:collect"), {"student": s.pk, "fee": row["fee"].pk,
                                                          "amount": str(row["balance"]), "mode": "upi"})
        self.assertEqual(FeePayment.objects.count(), before + 1)
        self.assertRedirects(resp, reverse("fees:receipt", args=[FeePayment.objects.order_by("-id").first().pk]))

    def test_enter_marks(self):
        self.login("teacher1")
        s = Student.objects.get(user__username="student1")
        exam = Exam.objects.get(name="Half-yearly")
        sub = s.classroom.subjects.first()
        self.client.post(reverse("exams:entry"), {"exam": exam.pk, "classroom": s.classroom_id, "subject": sub.pk,
                                                  f"m_{s.pk}": "88"})
        self.assertEqual(Mark.objects.get(exam=exam, student=s, subject=sub).marks, 88)

    def test_unpublished_results_hidden_from_parents(self):
        s = Student.objects.get(user__username="student1")
        exam = Exam.objects.get(name="Half-yearly")
        self.login("parent1")
        self.assertEqual(self.client.get(reverse("exams:report_card", args=[exam.pk, s.pk])).status_code, 403)

    def test_create_student_via_form(self):
        self.login("admin")
        s = Student.objects.first()
        resp = self.client.post(reverse("students:student_add"), {
            "admission_no": "NEW1", "first_name": "Test", "gender": "M", "date_of_birth": "2015-05-05",
            "classroom": s.classroom_id, "admission_date": "2026-06-01", "guardian_phone": "9000000000",
            "is_active": "on"})
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", {}) and resp.context["form"].errors)
        self.assertTrue(Student.objects.filter(admission_no="NEW1").exists())

    def test_sort_by_column_headings(self):
        self.login("admin")
        url = reverse("students:student_list")
        # columns: 0 Adm. No, 1 Name, 2 Class, 3 Roll, ...
        names = lambda r: [s.first_name for s in r.context["object_list"]]
        asc = self.client.get(url + "?sort=1")
        desc = self.client.get(url + "?sort=-1")
        self.assertEqual(names(asc), sorted(names(asc)))
        self.assertEqual(names(desc), sorted(names(desc), reverse=True))
        adm = [s.admission_no for s in self.client.get(url + "?sort=-0").context["object_list"]]
        self.assertEqual(adm, sorted(adm, reverse=True))
        # sort survives the class filter and a bad value is ignored
        cls = Student.objects.first().classroom_id
        r = self.client.get(url + f"?classroom={cls}&sort=3")
        rolls = [s.roll_no for s in r.context["object_list"]]
        self.assertEqual(rolls, sorted(rolls))
        self.assertEqual(self.client.get(url + "?sort=abc").status_code, 200)
        self.assertEqual(self.client.get(url + "?sort=99").status_code, 200)

    def test_every_list_column_sorts_without_error(self):
        self.login("admin")
        for name in ["students:student_list", "academics:class_list", "academics:subject_list",
                     "academics:year_list", "academics:tt_list", "staff:staff_list", "staff:salary_list",
                     "fees:type_list", "fees:structure_list", "exams:exam_list", "notices:notice_list",
                     "notices:event_list", "accounts:user_list"]:
            url = reverse(name)
            for h_i, h in enumerate(self.client.get(url).context["headers"]):
                if h["sortable"]:
                    for direction in ("", "-"):
                        r = self.client.get(f"{url}?sort={direction}{h_i}")
                        self.assertEqual(r.status_code, 200, f"{name} sort {direction}{h_i}")

    # ---- Student / parent logins managed from the student form ----
    def student_post_data(self, s, **extra):
        data = {"admission_no": s.admission_no, "first_name": s.first_name, "last_name": s.last_name,
                "gender": s.gender, "date_of_birth": s.date_of_birth.isoformat(), "classroom": s.classroom_id,
                "roll_no": s.roll_no or "", "admission_date": s.admission_date.isoformat(),
                "father_name": s.father_name, "mother_name": s.mother_name, "guardian_phone": s.guardian_phone,
                "is_active": "on",
                "student_username": s.user.username if s.user else "",
                "student_password": s.user.profile.issued_password if s.user else "",
                "parent_username": s.parent_user.username if s.parent_user else "",
                "parent_password": s.parent_user.profile.issued_password if s.parent_user else ""}
        data.update(extra)
        return data

    def test_profile_shows_logins_to_admin_only(self):
        s = Student.objects.get(user__username="student1")
        url = reverse("students:detail", args=[s.pk])
        self.login("admin")
        page = self.client.get(url).content.decode()
        for text in ("Login details", "student1", "student123", "parent1", "parent123"):
            self.assertIn(text, page)
        self.login("teacher1")
        self.assertNotIn("student123", self.client.get(url).content.decode())
        self.login("parent1")
        self.assertNotIn("parent123", self.client.get(url).content.decode())

    def test_edit_form_changes_logins(self):
        from django.contrib.auth import authenticate
        s = Student.objects.get(user__username="student1")
        self.login("admin")
        edit = reverse("students:student_edit", args=[s.pk])
        form = self.client.get(edit).context["form"]
        self.assertEqual(form["student_username"].value(), "student1")
        self.assertEqual(form["parent_password"].value(), "parent123")
        # unchanged form keeps the passwords working
        r = self.client.post(edit, self.student_post_data(s))
        self.assertEqual(r.status_code, 302, r.context and r.context["form"].errors)
        self.assertIsNotNone(authenticate(username="parent1", password="parent123"))
        # rename student login + new passwords
        r = self.client.post(edit, self.student_post_data(s, student_username="vignesh10a",
                                                         student_password="newpass1", parent_password="pp2024"))
        self.assertEqual(r.status_code, 302, r.context and r.context["form"].errors)
        self.assertIsNotNone(authenticate(username="vignesh10a", password="newpass1"))
        self.assertIsNone(authenticate(username="student1", password="student123"))
        self.assertIsNotNone(authenticate(username="parent1", password="pp2024"))
        page = self.client.get(reverse("students:detail", args=[s.pk])).content.decode()
        self.assertIn("vignesh10a", page)
        self.assertIn("pp2024", page)

    def test_new_student_logins_and_sibling_parent(self):
        from django.contrib.auth import authenticate
        self.login("admin")
        s = Student.objects.get(user__username="student1")
        base = self.student_post_data(s, admission_no="SIB1", first_name="Kavin",
                                      student_username="kavin1", student_password="kavin123",
                                      parent_username="parent1", parent_password="")
        r = self.client.post(reverse("students:student_add"), base)
        self.assertEqual(r.status_code, 302, r.context and r.context["form"].errors)
        sib = Student.objects.get(admission_no="SIB1")
        self.assertEqual(sib.parent_user, s.parent_user)                 # same parent login
        self.assertIsNotNone(authenticate(username="kavin1", password="kavin123"))
        self.assertIsNotNone(authenticate(username="parent1", password="parent123"))  # untouched
        self.login("parent1")
        self.assertEqual(len(self.client.get(reverse("accounts:dashboard")).context["children"]), 2)

    def test_login_form_validation(self):
        self.login("admin")
        s = Student.objects.exclude(user__username="student1").filter(user__isnull=True).first()
        edit = reverse("students:student_edit", args=[s.pk])
        # username of a teacher is refused
        r = self.client.post(edit, self.student_post_data(s, student_username="teacher1", student_password="abcd"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("student_username", r.context["form"].errors)
        # a new login needs a password
        r = self.client.post(edit, self.student_post_data(s, parent_username="newparent"))
        self.assertIn("parent_password", r.context["form"].errors)
        # student and parent can't share one username
        r = self.client.post(edit, self.student_post_data(s, student_username="same1", student_password="abcd",
                                                         parent_username="same1", parent_password="abcd"))
        self.assertIn("parent_username", r.context["form"].errors)

    def test_own_password_change_hides_issued_password(self):
        s = Student.objects.get(user__username="student1")
        self.login("parent1")
        self.client.post(reverse("accounts:password_change"), {
            "old_password": "parent123", "new_password1": "MySecret#2026", "new_password2": "MySecret#2026"})
        self.login_as = None
        self.client.logout()
        self.assertTrue(self.client.login(username="parent1", password="MySecret#2026"))
        self.login("admin")
        page = self.client.get(reverse("students:detail", args=[s.pk])).content.decode()
        self.assertIn("changed by user", page)
        self.assertNotIn("MySecret#2026", page)

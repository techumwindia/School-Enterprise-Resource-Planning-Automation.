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
             "student1": "student123"}


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

    def test_unpublished_results_hidden_from_students_and_parents(self):
        s = Student.objects.get(user__username="student1")
        exam = Exam.objects.get(name="Half-yearly")
        self.login("student1")
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

    # ---- One login per student, shared by student and parent ----
    def student_post_data(self, s, **extra):
        data = {"admission_no": s.admission_no, "first_name": s.first_name, "last_name": s.last_name,
                "gender": s.gender, "date_of_birth": s.date_of_birth.isoformat(), "classroom": s.classroom_id,
                "roll_no": s.roll_no or "", "admission_date": s.admission_date.isoformat(),
                "father_name": s.father_name, "mother_name": s.mother_name, "guardian_phone": s.guardian_phone,
                "is_active": "on",
                "login_username": s.user.username if s.user else "",
                "login_password": s.user.profile.issued_password if s.user else ""}
        data.update(extra)
        return data

    def test_profile_shows_login_to_admin_only(self):
        s = Student.objects.get(user__username="student1")
        url = reverse("students:detail", args=[s.pk])
        self.login("admin")
        page = self.client.get(url).content.decode()
        for text in ("Login (student &amp; parent)", "student1", "student123"):
            self.assertIn(text, page)
        self.assertNotIn("Parent login", page)
        for user in ("teacher1", "student1"):
            self.login(user)
            self.assertNotIn("student123", self.client.get(url).content.decode())

    def test_login_edited_from_profile_popup(self):
        from django.contrib.auth import authenticate
        s = Student.objects.get(user__username="student1")
        url = reverse("students:login_edit", args=[s.pk])
        self.login("admin")
        # the main student form no longer has login fields
        self.assertNotIn("login_username", self.client.get(reverse("students:student_edit", args=[s.pk])).context["form"].fields)
        form = self.client.get(url).context["form"]
        self.assertEqual(form["username"].value(), "student1")
        self.assertEqual(form["password"].value(), "student123")
        r = self.client.post(url, {"username": "vignesh10a", "password": "newpass1"})
        self.assertEqual(r.status_code, 204)
        self.assertIsNotNone(authenticate(username="vignesh10a", password="newpass1"))
        self.assertIsNone(authenticate(username="student1", password="student123"))
        s.refresh_from_db()
        self.assertEqual(s.user.username, "vignesh10a")
        # editing the student's details keeps the login
        r = self.client.post(reverse("students:student_edit", args=[s.pk]), self.student_post_data(s, roll_no="5"))
        self.assertEqual(r.status_code, 302)
        s.refresh_from_db()
        self.assertEqual((s.roll_no, s.user.username), (5, "vignesh10a"))
        # only admin
        for user in ("teacher1", "accountant", "student1"):
            self.client.logout()
            if user == "student1":
                self.client.login(username="vignesh10a", password="newpass1")
            else:
                self.login(user)
            self.assertEqual(self.client.get(url).status_code, 403, user)

    def test_login_popup_validation_and_create(self):
        self.login("admin")
        s = Student.objects.filter(user__isnull=True).first()
        url = reverse("students:login_edit", args=[s.pk])
        form = self.client.get(url).context["form"]
        self.assertEqual(form["username"].value(), s.admission_no.lower())   # suggested
        self.assertEqual(len(form["password"].value()), 8)
        r = self.client.post(url, {"username": "teacher1", "password": "abcd"})
        self.assertIn("username", r.context["form"].errors)
        r = self.client.post(url, {"username": "kid42", "password": "12"})
        self.assertIn("password", r.context["form"].errors)
        r = self.client.post(url, {"username": "kid42", "password": ""})  # blank -> generated
        self.assertEqual(r.status_code, 204)
        s.refresh_from_db()
        self.assertEqual(s.user.username, "kid42")
        self.assertEqual(len(s.user.profile.issued_password), 8)

    def test_own_password_change_hides_issued_password(self):
        s = Student.objects.get(user__username="student1")
        self.login("student1")
        self.client.post(reverse("accounts:password_change"), {
            "old_password": "student123", "new_password1": "MySecret#2026", "new_password2": "MySecret#2026"})
        self.client.logout()
        self.assertTrue(self.client.login(username="student1", password="MySecret#2026"))
        self.login("admin")
        page = self.client.get(reverse("students:detail", args=[s.pk])).content.decode()
        self.assertIn("changed by user", page)
        self.assertNotIn("MySecret#2026", page)

    def new_admission(self, adm, phone="9876543210", **extra):
        s = Student.objects.first()
        data = {"admission_no": adm, "first_name": "Test", "last_name": "K", "gender": "M",
                "date_of_birth": "2016-04-04", "classroom": s.classroom_id, "admission_date": "2026-06-01",
                "father_name": "Kumar", "guardian_phone": phone, "is_active": "on"}
        data.update(extra)
        return self.client.post(reverse("students:student_add"), data)

    def test_admission_generates_one_login(self):
        from django.contrib.auth import authenticate
        from django.contrib.auth.models import User
        self.login("admin")
        users_before = User.objects.count()
        r = self.new_admission("A2001")
        st = Student.objects.get(admission_no="A2001")
        self.assertRedirects(r, reverse("students:detail", args=[st.pk]))
        self.assertEqual(User.objects.count(), users_before + 1)       # only one account
        self.assertIsNone(st.parent_user)
        self.assertEqual(st.user.username, "a2001")
        pw = st.user.profile.issued_password
        self.assertEqual(len(pw), 8)
        self.assertIsNotNone(authenticate(username="a2001", password=pw))
        self.assertIn(pw, self.client.get(reverse("students:detail", args=[st.pk])).content.decode())
        # login sees the child's dashboard
        self.client.logout()
        self.client.login(username="a2001", password=pw)
        self.assertEqual(self.client.get(reverse("accounts:dashboard")).context["children"][0]["student"], st)
        # same admission no pattern taken -> unique suffix
        self.login("admin")
        User.objects.create_user("a2004", password="x")
        self.new_admission("A2004")
        self.assertEqual(Student.objects.get(admission_no="A2004").user.username, "a2004-2")

    def test_create_missing_logins_button(self):
        self.login("admin")
        missing = Student.objects.filter(is_active=True, user__isnull=True).count()
        self.assertGreater(missing, 100)
        self.client.get(reverse("students:generate_logins"))  # GET does nothing
        self.assertEqual(Student.objects.filter(user__isnull=True).count(), missing)
        for _ in range(2):  # batches of 100 per click
            r = self.client.post(reverse("students:generate_logins"))
            self.assertRedirects(r, reverse("students:student_list"))
        self.assertFalse(Student.objects.filter(is_active=True, user__isnull=True).exists())
        self.assertFalse(Student.objects.filter(parent_user__isnull=False).exclude(user__username="student1").exists())
        self.assertTrue(self.client.login(username="student1", password="student123"))  # untouched
        self.login("teacher1")
        self.assertEqual(self.client.post(reverse("students:generate_logins")).status_code, 403)

    def test_profile_card_shows_once_for_every_role(self):
        s = Student.objects.get(user__username="student1")
        for user in ("admin", "teacher1", "accountant", "student1"):
            self.login(user)
            page = self.client.get(reverse("students:detail", args=[s.pk])).content.decode()
            self.assertEqual(page.count('<div class="card-header">Profile</div>'), 1, user)
            self.assertIn(s.father_name, page, user)
            self.assertEqual(page.count("Login (student &amp; parent)"), 1 if user == "admin" else 0, user)

    def test_profile_has_no_main_edit_button_and_view_buttons(self):
        s = Student.objects.get(user__username="student1")
        self.login("admin")
        page = self.client.get(reverse("students:detail", args=[s.pk])).content.decode()
        self.assertNotIn(reverse("students:student_edit", args=[s.pk]), page)
        for name in ("fees_detail", "attendance_detail", "results_detail", "login_edit"):
            self.assertIn(reverse(f"students:{name}", args=[s.pk]), page)

    def test_view_popups(self):
        s = Student.objects.get(user__username="student1")
        other = Student.objects.exclude(pk=s.pk).first()
        urls = {n: reverse(f"students:{n}", args=[s.pk]) for n in ("fees_detail", "attendance_detail", "results_detail")}
        for user in ("admin", "teacher1", "accountant", "student1"):
            self.login(user)
            for name, url in urls.items():
                self.assertEqual(self.client.get(url).status_code, 200, f"{user} {name}")
        # fee popup content: statuses, receipts with view + pdf
        self.login("admin")
        r = self.client.get(urls["fees_detail"])
        page = r.content.decode()
        p = FeePayment.objects.filter(student=s).first()
        self.assertIn(p.receipt_no, page)
        self.assertIn(f'data-pdf="{reverse("fees:receipt", args=[p.pk])}"', page)
        self.assertTrue({row["status"] for row in r.context["ledger"]["rows"]} <= {"Paid", "Overdue", "Partly paid", "Not yet due", "Due"})
        # attendance popup: months and counts match the records
        r = self.client.get(urls["attendance_detail"])
        self.assertEqual(r.context["total"], s.attendance.count())
        self.assertEqual(sum(m["total"] for m in r.context["months"]), s.attendance.count())
        # results: staff see unpublished exams too, students only published
        Mark.objects.create(exam=Exam.objects.get(name="Half-yearly"), student=s,
                            subject=s.classroom.subjects.first(), marks=70)
        self.assertEqual(len(self.client.get(urls["results_detail"]).context["blocks"]), 2)
        self.login("student1")
        blocks = self.client.get(urls["results_detail"]).context["blocks"]
        self.assertEqual([b["exam"].name for b in blocks], ["Quarterly"])
        # another student's popups are blocked
        for n in ("fees_detail", "attendance_detail", "results_detail"):
            self.assertEqual(self.client.get(reverse(f"students:{n}", args=[other.pk])).status_code, 403)

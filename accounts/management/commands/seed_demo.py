"""
Load realistic demo data:  python manage.py seed_demo
Creates classes 1–10, staff, ~120 students, fee structure, payments,
3 weeks of attendance, a published exam with marks, timetable, notices
and five demo logins (see README).
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicYear, ClassRoom, Subject, TimetableEntry
from accounts.models import Role
from attendance.models import Attendance
from exams.models import Exam, Mark
from fees.models import FeePayment, FeeStructure, FeeType
from notices.models import Event, Notice
from staff.models import SalaryPayment, Staff
from students.models import Student

BOYS = ["Arun", "Karthik", "Surya", "Vignesh", "Harish", "Pranav", "Dinesh", "Mohan", "Ravi", "Siva",
        "Gokul", "Naveen", "Ajay", "Bala", "Hari", "Kavin", "Madhan", "Sanjay", "Tharun", "Yuvan"]
GIRLS = ["Priya", "Divya", "Kavya", "Nandhini", "Swetha", "Harini", "Meena", "Pooja", "Sowmya", "Yazhini",
         "Abinaya", "Bhavani", "Deepika", "Janani", "Keerthana", "Lavanya", "Monisha", "Revathi", "Sneha", "Vaishnavi"]
INITIALS = ["R", "S", "M", "K", "P", "A", "T", "V", "G", "N"]
FATHERS = ["Ramesh", "Suresh", "Murugan", "Kannan", "Palani", "Arumugam", "Selvam", "Velmurugan", "Ganesan", "Natarajan"]
MOTHERS = ["Lakshmi", "Selvi", "Meenakshi", "Kamala", "Parvathi", "Vasanthi", "Malathi", "Jeya", "Revathi", "Saraswathi"]
TOWNS = ["Sivakasi", "Virudhunagar", "Thiruthangal", "Sattur", "Srivilliputhur"]

SUBJECTS = [("Tamil", "TAM"), ("English", "ENG"), ("Mathematics", "MAT"), ("Science", "SCI"),
            ("Social Science", "SOC"), ("Computer Science", "CS"), ("Physical Education", "PE")]


class Command(BaseCommand):
    help = "Load demo data for the School ERP"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Load even if students already exist")

    @transaction.atomic
    def handle(self, *args, force=False, **opts):
        if Student.objects.exists() and not force:
            self.stdout.write(self.style.WARNING("Data already exists. Use --force to add demo data anyway."))
            return
        rnd = random.Random(42)
        today = timezone.localdate()

        year, _ = AcademicYear.objects.get_or_create(
            name=f"{today.year if today.month >= 6 else today.year - 1}-{str((today.year if today.month >= 6 else today.year - 1) + 1)[-2:]}",
            defaults={"start_date": date(today.year if today.month >= 6 else today.year - 1, 6, 1),
                      "end_date": date((today.year if today.month >= 6 else today.year - 1) + 1, 4, 30),
                      "is_current": True})

        subjects = {code: Subject.objects.get_or_create(code=code, defaults={"name": name})[0] for name, code in SUBJECTS}
        core = [subjects[c] for c in ("TAM", "ENG", "MAT", "SCI", "SOC")]

        # Staff
        teacher_names = ["Mrs. Jeyalakshmi", "Mr. Senthil Kumar", "Mrs. Anitha", "Mr. Rajesh", "Mrs. Saranya",
                         "Mr. Muthukumar", "Mrs. Kalaivani", "Mr. Prabhu", "Mrs. Vijayalakshmi", "Mr. Balamurugan",
                         "Mrs. Uma", "Mr. Saravanan"]
        designations = ["PG Assistant", "BT Assistant", "BT Assistant", "Secondary Grade Teacher"]
        teach_subj = ["TAM", "ENG", "MAT", "SCI", "SOC", "CS", "PE", "TAM", "ENG", "MAT", "SCI", "SOC"]
        staff = []
        for i, name in enumerate(teacher_names, 1):
            st = Staff.objects.create(
                employee_id=f"EMP{i:03d}", name=name, gender="F" if name.startswith("Mrs") else "M",
                designation=designations[i % 4], qualification=rnd.choice(["M.Sc., B.Ed.", "M.A., B.Ed.", "B.Sc., B.Ed."]),
                phone=f"9{rnd.randint(100000000, 999999999)}", date_of_joining=date(2015 + i % 9, 6, 1),
                monthly_salary=Decimal(rnd.choice([18000, 22000, 25000, 28000, 32000])))
            st.subjects.add(subjects[teach_subj[i - 1]])
            staff.append(st)
        office = Staff.objects.create(employee_id="EMP101", name="Mr. Ganesh", category=Staff.ROLE_NON_TEACHING,
                                      designation="Office Assistant / Accountant", phone="9876501234",
                                      monthly_salary=Decimal(15000))
        by_subject = {}
        for st in staff:
            for sub in st.subjects.all():
                by_subject.setdefault(sub.code, []).append(st)

        # Classes 1–10, section A
        classes = []
        for n in range(1, 11):
            c = ClassRoom.objects.create(grade=str(n), section="A", order=n + 1, room_no=f"{100 + n}",
                                         class_teacher=staff[(n - 1) % len(staff)])
            c.subjects.set(core + ([subjects["CS"]] if n >= 6 else []) + [subjects["PE"]])
            classes.append(c)

        # Timetable: 6 days × 7 periods
        for c in classes:
            subs = list(c.subjects.all())
            for d in range(1, 7):
                periods = 4 if d == 6 else 7
                for p in range(1, periods + 1):
                    sub = subs[(d + p + c.order) % len(subs)]
                    TimetableEntry.objects.create(classroom=c, day=d, period=p, subject=sub,
                                                  teacher=rnd.choice(by_subject.get(sub.code, staff)))

        # Students: 12 per class
        adm = 1000
        students = []
        for c in classes:
            for roll in range(1, 13):
                adm += 1
                g = "M" if roll % 2 else "F"
                first = rnd.choice(BOYS if g == "M" else GIRLS)
                age = int(c.grade) + 5
                students.append(Student.objects.create(
                    admission_no=f"A{adm}", emis_no=f"33{rnd.randint(10**12, 10**13 - 1)}",
                    first_name=first, last_name=rnd.choice(INITIALS), gender=g,
                    date_of_birth=date(today.year - age, rnd.randint(1, 12), rnd.randint(1, 28)),
                    blood_group=rnd.choice(Student.BLOOD)[0], classroom=c, roll_no=roll,
                    admission_date=date(today.year - rnd.randint(0, int(c.grade)), 6, 3),
                    father_name=rnd.choice(FATHERS), mother_name=rnd.choice(MOTHERS),
                    guardian_phone=f"9{rnd.randint(100000000, 999999999)}",
                    address=f"{rnd.randint(1, 120)}, {rnd.choice(['Main Road', 'North Street', 'Gandhi Nagar', 'Nehru Colony'])}, {rnd.choice(TOWNS)}",
                    uses_transport=rnd.random() < 0.4))

        # Fees
        tuition = FeeType.objects.get_or_create(name="Tuition Fee")[0]
        exam_fee = FeeType.objects.get_or_create(name="Exam Fee")[0]
        bus = FeeType.objects.get_or_create(name="Bus Fee", defaults={"transport_only": True})[0]
        books = FeeType.objects.get_or_create(name="Books & Uniform")[0]
        y0 = year.start_date.year
        terms = [("Term 1", date(y0, 6, 30)), ("Term 2", date(y0, 10, 15)), ("Term 3", date(y0 + 1, 1, 15))]
        for c in classes:
            base = 6000 + int(c.grade) * 800
            for t, due in terms:
                FeeStructure.objects.create(academic_year=year, classroom=c, fee_type=tuition, term=t, amount=base, due_date=due)
                FeeStructure.objects.create(academic_year=year, classroom=c, fee_type=bus, term=t, amount=3500, due_date=due)
            FeeStructure.objects.create(academic_year=year, classroom=c, fee_type=exam_fee, term="Annual", amount=600, due_date=date(y0, 9, 1))
            FeeStructure.objects.create(academic_year=year, classroom=c, fee_type=books, term="Annual", amount=2500, due_date=date(y0, 6, 15))

        admin_user = self._user("admin", "admin123", Role.ADMIN, "School", "Admin", superuser=True)
        acct_user = self._user("accountant", "accounts123", Role.ACCOUNTANT, "Ganesh", "")
        office.user = acct_user
        office.save()

        from fees.models import fee_ledger
        modes = ["cash", "cash", "upi", "upi", "bank"]
        for s in students:
            for row in fee_ledger(s, year)["rows"]:
                fee = row["fee"]
                if fee.due_date and fee.due_date > today:
                    continue
                if rnd.random() < 0.82:
                    pay_day = min(today, fee.due_date + timedelta(days=rnd.randint(-10, 20))) if fee.due_date else today
                    if rnd.random() < 0.15:  # some recent payments for the dashboard trend
                        pay_day = today - timedelta(days=rnd.randint(0, 6))
                    amt = fee.amount if rnd.random() < 0.85 else (fee.amount / 2).quantize(Decimal("1"))
                    FeePayment.objects.create(student=s, fee=fee, amount=amt, paid_on=pay_day,
                                              mode=rnd.choice(modes), collected_by=acct_user)

        # Attendance: last 15 school days
        d, marked = today, 0
        while marked < 15:
            if d.weekday() != 6:
                for s in students:
                    r = rnd.random()
                    status = "P" if r < 0.9 else "A" if r < 0.96 else "L" if r < 0.99 else "H"
                    Attendance.objects.create(student=s, date=d, status=status, marked_by=admin_user)
                marked += 1
            d -= timedelta(days=1)

        # Exams
        quarterly = Exam.objects.create(name="Quarterly", academic_year=year, start_date=date(y0, 9, 15), is_published=True)
        Exam.objects.create(name="Half-yearly", academic_year=year, start_date=date(y0, 12, 10))
        for s in students:
            ability = rnd.uniform(0.35, 0.95)
            for sub in s.classroom.subjects.exclude(code="PE"):
                if rnd.random() < 0.02:
                    Mark.objects.create(exam=quarterly, student=s, subject=sub, absent=True)
                else:
                    m = max(5, min(100, round(rnd.gauss(ability * 100, 10))))
                    Mark.objects.create(exam=quarterly, student=s, subject=sub, marks=m)

        # Salary for last month
        last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        for st in staff + [office]:
            SalaryPayment.objects.create(staff=st, month=last_month, basic=st.monthly_salary,
                                         allowances=Decimal(1500), deductions=Decimal(rnd.choice([0, 500, 1200])),
                                         paid_on=last_month.replace(day=28))

        # Notices & events
        Notice.objects.create(title="Half-yearly examination timetable", is_pinned=True, created_by=admin_user,
                              body="Half-yearly examinations begin on 10 December. The detailed timetable has been shared with class teachers.")
        Notice.objects.create(title="Term 2 fee reminder", audience="students", created_by=admin_user,
                              body="Parents are requested to clear the Term 2 tuition fee at the earliest. UPI payments are accepted at the office.")
        Notice.objects.create(title="Staff meeting on Friday", audience="staff", created_by=admin_user,
                              body="All teaching staff meet in the library at 3:45 PM to plan the annual day programme.")
        for title, delta, hol in [("Parent–Teacher Meeting", 4, False), ("Science Exhibition", 12, False),
                                  ("Christmas holiday", 38, True), ("Annual Day", 55, False), ("Pongal holidays", 57, True)]:
            Event.objects.create(title=title, date=today + timedelta(days=delta), is_holiday=hol)

        # Logins
        t = self._user("teacher1", "teacher123", Role.TEACHER, "Jeyalakshmi", "")
        staff[0].user = t
        staff[0].save()
        stu = students[-12]  # first student of class 10
        stu.user = self._user("student1", "student123", Role.STUDENT, stu.first_name, stu.last_name)
        stu.parent_user = self._user("parent1", "parent123", Role.PARENT, stu.father_name, "")
        stu.save()

        self.stdout.write(self.style.SUCCESS(
            f"Demo data loaded: {len(classes)} classes, {len(students)} students, {len(staff) + 1} staff.\n"
            "Logins: admin/admin123 · teacher1/teacher123 · accountant/accounts123 · "
            "student1/student123 · parent1/parent123"))

    def _user(self, username, password, role, first, last, superuser=False):
        u, _ = User.objects.get_or_create(username=username, defaults={"first_name": first, "last_name": last})
        u.set_password(password)
        u.is_superuser = u.is_staff = superuser
        u.save()
        u.profile.role = role
        u.profile.issued_password = password
        u.profile.save()
        return u

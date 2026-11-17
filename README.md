# School ERP — School Enterprise Resource Planning Automation

A complete school-level ERP web application built with **Django 5**. It covers day-to-day school office work: admissions, classes, timetable, attendance, fees with printed receipts, exams with report cards, staff salary, and a notice board. Each role (admin, teacher, accountant, student, parent) gets its own login and dashboard.

## Modules

| Module | What it does |
|---|---|
| **Dashboard** | Student/staff counts, today's attendance %, fee collection (today, month, 7-day chart), absentees with parent phone, recent receipts, class strength, notices and events. Teachers see their periods for the day. Students/parents see attendance %, fee balance, results and today's timetable. |
| **Students** | Admission register (admission no., EMIS no., DOB, blood group, parents, phone, address, school bus), search and filter by class, full profile page, CSV export. |
| **Classes & Subjects** | Class + section, class teacher, room, subjects per class, class page with student list and timetable. |
| **Timetable** | Weekly grid per class (Mon–Sat × periods) with subject and teacher, printable. |
| **Attendance** | One-screen marking per class (Present / Absent / Leave / Half-day, "All present" shortcut), edit past days, monthly register with % and below-75% highlighting. Future dates are blocked. |
| **Fees** | Fee types (with bus-only fees), fee structure per class/term with due dates, collect fees by searching name/admission no./phone, part payments and concessions, auto receipt numbers (`R2611xxxx`), printable receipt, payment register with date/mode filters, pending dues report with overdue amounts. |
| **Exams** | Exams per academic year, subject-wise marks entry per class (with absent), class result sheet with total, %, grade (A1–E), rank and pass %, printable report card. Results are visible to students/parents only after the admin publishes the exam. |
| **Staff & Salary** | Staff register (teaching / non-teaching, subjects, salary), monthly salary payments, printable payslip. |
| **Notices & Events** | Notice board with audience (everyone / staff / students & parents), pinned notices, events & holidays calendar. |
| **User accounts** | Admin creates logins and links them to staff/student records. |

## Roles and access

| Role | Can use |
|---|---|
| Admin | Everything, including setup (years, subjects, fee types, users) |
| Teacher | Students (view), classes, timetable, mark attendance, attendance report, enter marks, results |
| Accountant | Students (view), collect fees, payments, dues, fee structure, salary/payslips |
| Student | Own dashboard, profile, attendance, fees/receipts, published report cards |
| Parent | Same as student, for each linked child |

Linking logins: create the user under **User Accounts**, then open the student/staff record and pick it in *User* (student login), *Parent user* (parent login) or *User* on a staff record (teacher login).

## Run it locally (Windows / Linux)

```bash
python -m venv venv
venv\Scripts\activate            # Linux: source venv/bin/activate
pip install Django whitenoise python-dotenv
python manage.py migrate
python manage.py seed_demo       # optional demo data
python manage.py runserver
```

Open http://127.0.0.1:8000 and sign in. Demo logins created by `seed_demo`:

| Username | Password | Role |
|---|---|---|
| admin | admin123 | Admin |
| teacher1 | teacher123 | Teacher (class teacher of 1-A) |
| accountant | accounts123 | Accountant |
| student1 | student123 | Student (class 10-A) |
| parent1 | parent123 | Parent of student1 |

For a real school, skip `seed_demo` and create the first admin with `python manage.py createsuperuser`. Then set up in this order: **Academic Years → Subjects → Staff → Classes → Students → Fee Types → Fee Structure → Exams**.

Run the tests with `python manage.py test`.

## Deploy on the VPS (Nginx + Gunicorn + MySQL)

Same setup as the other sites on the server; this app uses port **8005**.

```bash
# 1. Code and virtualenv
sudo git clone https://github.com/techumwindia/School-Enterprise-Resource-Planning-Automation. /var/www/school-erp
cd /var/www/school-erp
sudo apt install -y python3-venv python3-dev default-libmysqlclient-dev build-essential pkg-config
python3 -m venv venv && venv/bin/pip install -r requirements.txt

# 2. Database
sudo mysql -e "CREATE DATABASE school_erp CHARACTER SET utf8mb4; \
  CREATE USER 'school_erp'@'localhost' IDENTIFIED BY 'strong-password'; \
  GRANT ALL ON school_erp.* TO 'school_erp'@'localhost'; FLUSH PRIVILEGES;"

# 3. Settings
cp .env.example .env && nano .env      # secret key, domain, school name, DB password
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
venv/bin/python manage.py createsuperuser
sudo chown -R www-data:www-data /var/www/school-erp

# 4. Service + Nginx
sudo cp deploy/school-erp.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now school-erp
sudo cp deploy/nginx-school-erp.conf /etc/nginx/sites-available/school-erp
sudo ln -s /etc/nginx/sites-available/school-erp /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d erp.yourschool.in   # HTTPS
```

Update later with (run once first: `git config --global --add safe.directory /var/www/school-erp`): `git pull && venv/bin/pip install -r requirements.txt && venv/bin/python manage.py migrate && venv/bin/python manage.py collectstatic --noinput && sudo systemctl restart school-erp`.

Generate a secret key with: `python -c "import secrets; print(secrets.token_urlsafe(50))"`.

## Project layout

```
school_erp/      settings, urls
accounts/        roles, login, dashboard, users, shared CRUD helpers, seed_demo, tests
academics/       academic years, subjects, classes, timetable
students/        student register and profile
staff/           staff register, salary, payslips
attendance/      daily marking and monthly report
fees/            fee types/structure, collection, receipts, dues
exams/           exams, marks, results, report cards
notices/         notice board, events and holidays
templates/       all HTML pages (Bootstrap 5, bundled locally — no CDN needed)
static/          CSS and vendored Bootstrap / Bootstrap Icons
deploy/          systemd and Nginx config
```

The Django admin is also available at `/django-admin/` for superusers.

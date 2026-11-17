from django.conf import settings
from django.db import models


class Staff(models.Model):
    ROLE_TEACHING = "teaching"
    ROLE_NON_TEACHING = "non_teaching"
    CATEGORY = [(ROLE_TEACHING, "Teaching"), (ROLE_NON_TEACHING, "Non-teaching")]
    GENDER = [("M", "Male"), ("F", "Female"), ("O", "Other")]

    employee_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    gender = models.CharField(max_length=1, choices=GENDER, default="M")
    category = models.CharField(max_length=20, choices=CATEGORY, default=ROLE_TEACHING)
    designation = models.CharField(max_length=80, help_text="e.g. PG Assistant, BT Assistant, Clerk")
    qualification = models.CharField(max_length=120, blank=True)
    subjects = models.ManyToManyField("academics.Subject", blank=True, related_name="teachers")
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    date_of_joining = models.DateField(null=True, blank=True)
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="staff", help_text="Login account (optional)")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "staff"

    def __str__(self):
        return f"{self.name} ({self.employee_id})"


class SalaryPayment(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="salary_payments")
    month = models.DateField(help_text="Any date in the salary month")
    basic = models.DecimalField(max_digits=10, decimal_places=2)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_on = models.DateField()
    remarks = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-month", "staff__name"]

    @property
    def net_pay(self):
        return self.basic + self.allowances - self.deductions

    def __str__(self):
        return f"{self.staff.name} - {self.month:%b %Y}"

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class FeeType(models.Model):
    name = models.CharField(max_length=80, unique=True, help_text="e.g. Tuition Fee, Bus Fee, Exam Fee")
    transport_only = models.BooleanField(default=False, help_text="Only charged to students who use the school bus")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class FeeStructure(models.Model):
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.CASCADE)
    classroom = models.ForeignKey("academics.ClassRoom", on_delete=models.CASCADE, related_name="fees",
                                  verbose_name="class")
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE)
    term = models.CharField(max_length=40, default="Annual", help_text="e.g. Term 1, Term 2, Annual")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["classroom__order", "classroom__section", "due_date", "fee_type__name"]
        unique_together = ("academic_year", "classroom", "fee_type", "term")

    def __str__(self):
        return f"{self.classroom} · {self.fee_type} · {self.term} (₹{self.amount})"


class FeePayment(models.Model):
    MODES = [("cash", "Cash"), ("upi", "UPI"), ("card", "Card"), ("bank", "Bank transfer"), ("cheque", "Cheque")]

    receipt_no = models.CharField(max_length=30, unique=True, editable=False)
    student = models.ForeignKey("students.Student", on_delete=models.PROTECT, related_name="payments")
    fee = models.ForeignKey(FeeStructure, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    concession = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_on = models.DateField(default=timezone.localdate)
    mode = models.CharField(max_length=10, choices=MODES, default="cash")
    reference = models.CharField(max_length=60, blank=True, help_text="UPI ref / cheque no.")
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    remarks = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-paid_on", "-id"]

    def __str__(self):
        return f"{self.receipt_no} - {self.student.full_name}"

    def save(self, *args, **kwargs):
        if not self.receipt_no:
            prefix = f"R{self.paid_on:%y%m}"
            last = FeePayment.objects.filter(receipt_no__startswith=prefix).order_by("-receipt_no").first()
            seq = int(last.receipt_no[len(prefix):]) + 1 if last else 1
            self.receipt_no = f"{prefix}{seq:04d}"
        super().save(*args, **kwargs)


def applicable_fees(student, year=None):
    from academics.models import AcademicYear
    year = year or AcademicYear.current()
    if not student.classroom_id or not year:
        return FeeStructure.objects.none()
    qs = FeeStructure.objects.filter(classroom=student.classroom, academic_year=year).select_related("fee_type")
    if not student.uses_transport:
        qs = qs.exclude(fee_type__transport_only=True)
    return qs


def fee_ledger(student, year=None):
    """Rows of (fee, paid, balance) plus totals for one student."""
    rows, total_due, total_paid = [], Decimal(0), Decimal(0)
    for fee in applicable_fees(student, year):
        agg = fee.payments.filter(student=student).aggregate(a=Sum("amount"), c=Sum("concession"))
        paid = (agg["a"] or 0) + (agg["c"] or 0)
        bal = fee.amount - paid
        rows.append({"fee": fee, "paid": paid, "balance": bal,
                     "overdue": bal > 0 and fee.due_date and fee.due_date < timezone.localdate()})
        total_due += fee.amount
        total_paid += paid
    return {"rows": rows, "total": total_due, "paid": total_paid, "balance": total_due - total_paid}

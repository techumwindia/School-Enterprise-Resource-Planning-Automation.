from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from academics.models import AcademicYear, ClassRoom
from accounts.crud import make_crud
from accounts.models import Role
from accounts.permissions import role_required
from students.models import Student
from students.views import can_view_student

from .models import FeePayment, FeeStructure, FeeType, fee_ledger

FEE_ROLES = (Role.ADMIN, Role.ACCOUNTANT)

FeeTypeViews = make_crud(
    FeeType, title="Fee Types", url_prefix="fees:type", fields=["name", "transport_only"],
    columns=(("Fee type", "name"), ("School bus only", "transport_only")), roles=FEE_ROLES,
)


def _class_choices():
    return [(c.pk, str(c)) for c in ClassRoom.objects.all()]


StructureViews = make_crud(
    FeeStructure, title="Fee Structure", url_prefix="fees:structure",
    fields=["academic_year", "classroom", "fee_type", "term", "amount", "due_date"],
    columns=(("Year", "academic_year"), ("Class", "classroom"), ("Fee type", "fee_type"), ("Term", "term"),
             ("Amount (₹)", "amount"), ("Due date", "due_date")),
    list_filters=(("classroom", "classroom_id", _class_choices, "Class"),),
    select_related=("academic_year", "classroom", "fee_type"), roles=FEE_ROLES,
)


@role_required(*FEE_ROLES)
def collect(request):
    q = request.GET.get("q", "").strip()
    results = []
    if q:
        results = Student.objects.filter(
            Q(admission_no__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(guardian_phone__icontains=q), is_active=True).select_related("classroom")[:20]
        if len(results) == 1:
            return redirect(f"{request.path}?student={results[0].pk}")

    student = None
    ledger = None
    if request.GET.get("student") or request.POST.get("student"):
        student = get_object_or_404(Student, pk=request.GET.get("student") or request.POST.get("student"))
        ledger = fee_ledger(student)

    if request.method == "POST" and student:
        fee = get_object_or_404(FeeStructure, pk=request.POST.get("fee"))
        row = next((r for r in ledger["rows"] if r["fee"].pk == fee.pk), None)
        try:
            amount = Decimal(request.POST.get("amount") or "0")
            concession = Decimal(request.POST.get("concession") or "0")
        except InvalidOperation:
            amount = concession = Decimal("-1")
        if row is None:
            messages.error(request, "That fee does not apply to this student.")
        elif amount < 0 or concession < 0 or amount + concession <= 0:
            messages.error(request, "Enter a valid amount.")
        elif amount + concession > row["balance"]:
            messages.error(request, f"Amount exceeds the balance of ₹{row['balance']}.")
        else:
            p = FeePayment.objects.create(
                student=student, fee=fee, amount=amount, concession=concession,
                paid_on=parse_date(request.POST.get("paid_on") or "") or timezone.localdate(),
                mode=request.POST.get("mode", "cash"), reference=request.POST.get("reference", ""),
                remarks=request.POST.get("remarks", ""), collected_by=request.user)
            messages.success(request, f"Payment recorded. Receipt {p.receipt_no}.")
            return redirect("fees:receipt", pk=p.pk)

    return render(request, "fees/collect.html", {
        "q": q, "results": results, "student": student, "ledger": ledger,
        "modes": FeePayment.MODES, "today": timezone.localdate(),
    })


@login_required
def receipt(request, pk):
    p = get_object_or_404(FeePayment.objects.select_related("student", "student__classroom", "fee__fee_type",
                                                            "collected_by"), pk=pk)
    if not can_view_student(request.user, p.student):
        raise PermissionDenied
    return render(request, "fees/receipt.html", {"p": p, "total": p.amount + p.concession})


@role_required(*FEE_ROLES)
def payments(request):
    qs = FeePayment.objects.select_related("student", "student__classroom", "fee__fee_type")
    start = parse_date(request.GET.get("from") or "")
    end = parse_date(request.GET.get("to") or "")
    if start:
        qs = qs.filter(paid_on__gte=start)
    if end:
        qs = qs.filter(paid_on__lte=end)
    if request.GET.get("mode"):
        qs = qs.filter(mode=request.GET["mode"])
    if request.GET.get("q"):
        q = request.GET["q"]
        qs = qs.filter(Q(receipt_no__icontains=q) | Q(student__first_name__icontains=q) |
                       Q(student__admission_no__icontains=q))
    totals = qs.aggregate(amount=Sum("amount"), concession=Sum("concession"))
    by_mode = qs.values("mode").annotate(total=Sum("amount")).order_by("mode")
    return render(request, "fees/payments.html", {
        "payments": qs[:500], "totals": totals, "by_mode": by_mode, "modes": FeePayment.MODES,
        "f": request.GET,
    })


@role_required(*FEE_ROLES)
def dues(request):
    classes = ClassRoom.objects.all()
    classroom = classes.filter(pk=request.GET.get("classroom")).first()
    students = Student.objects.filter(is_active=True).select_related("classroom")
    if classroom:
        students = students.filter(classroom=classroom)
    rows, grand = [], Decimal(0)
    for s in students:
        led = fee_ledger(s)
        if led["balance"] > 0:
            overdue = sum((r["balance"] for r in led["rows"] if r["overdue"]), Decimal(0))
            rows.append({"s": s, "total": led["total"], "paid": led["paid"], "balance": led["balance"],
                         "overdue": overdue})
            grand += led["balance"]
    rows.sort(key=lambda r: -r["balance"])
    return render(request, "fees/dues.html", {"classes": classes, "classroom": classroom, "rows": rows,
                                              "grand": grand, "year": AcademicYear.current()})

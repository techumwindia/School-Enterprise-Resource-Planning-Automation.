from django.db import models


class Exam(models.Model):
    name = models.CharField(max_length=80, help_text="e.g. Quarterly, Half-yearly, Annual")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.CASCADE)
    start_date = models.DateField(null=True, blank=True)
    max_marks = models.PositiveSmallIntegerField(default=100)
    pass_marks = models.PositiveSmallIntegerField(default=35)
    is_published = models.BooleanField(default=False, help_text="Students and parents can see results")

    class Meta:
        ordering = ["-academic_year__start_date", "start_date"]
        unique_together = ("name", "academic_year")

    def __str__(self):
        return f"{self.name} {self.academic_year}"


class Mark(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="marks")
    subject = models.ForeignKey("academics.Subject", on_delete=models.CASCADE)
    marks = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    absent = models.BooleanField(default=False)

    class Meta:
        unique_together = ("exam", "student", "subject")

    def __str__(self):
        return f"{self.student} {self.subject} {self.marks}"


def grade_for(percent):
    if percent is None:
        return "-"
    for cutoff, g in ((91, "A1"), (81, "A2"), (71, "B1"), (61, "B2"), (51, "C1"), (41, "C2"), (35, "D")):
        if percent >= cutoff:
            return g
    return "E"

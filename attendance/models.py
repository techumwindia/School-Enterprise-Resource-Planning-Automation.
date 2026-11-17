from django.conf import settings
from django.db import models


class Attendance(models.Model):
    PRESENT, ABSENT, LEAVE, HALF_DAY = "P", "A", "L", "H"
    STATUS = [(PRESENT, "Present"), (ABSENT, "Absent"), (LEAVE, "Leave"), (HALF_DAY, "Half day")]

    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(db_index=True)
    status = models.CharField(max_length=1, choices=STATUS, default=PRESENT)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("student", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.student} {self.date} {self.status}"


def attendance_percent(qs):
    """Present + half of half-days, over total marked days."""
    total = qs.count()
    if not total:
        return None
    present = qs.filter(status=Attendance.PRESENT).count()
    half = qs.filter(status=Attendance.HALF_DAY).count()
    return round((present + half * 0.5) * 100 / total, 1)

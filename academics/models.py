from django.db import models


class AcademicYear(models.Model):
    name = models.CharField(max_length=20, unique=True, help_text="e.g. 2026-27")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            AcademicYear.objects.exclude(pk=self.pk).update(is_current=False)

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first() or cls.objects.first()


class Subject(models.Model):
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ClassRoom(models.Model):
    """A class + section, e.g. 10 - A."""
    grade = models.CharField("Class", max_length=20, help_text="e.g. LKG, 1, 10, 12")
    section = models.CharField(max_length=5, default="A")
    order = models.PositiveSmallIntegerField(default=0, help_text="Sort order (LKG=0, UKG=1, 1=2 ...)")
    class_teacher = models.ForeignKey("staff.Staff", null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="class_teacher_of")
    room_no = models.CharField(max_length=20, blank=True)
    subjects = models.ManyToManyField(Subject, blank=True, related_name="classes")

    class Meta:
        ordering = ["order", "grade", "section"]
        unique_together = ("grade", "section")
        verbose_name = "class"

    def __str__(self):
        return f"{self.grade} - {self.section}"

    @property
    def student_count(self):
        return self.students.filter(is_active=True).count()


class TimetableEntry(models.Model):
    DAYS = [(1, "Monday"), (2, "Tuesday"), (3, "Wednesday"), (4, "Thursday"), (5, "Friday"), (6, "Saturday")]
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="timetable")
    day = models.PositiveSmallIntegerField(choices=DAYS)
    period = models.PositiveSmallIntegerField()
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey("staff.Staff", null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="timetable")

    class Meta:
        ordering = ["classroom", "day", "period"]
        unique_together = ("classroom", "day", "period")
        verbose_name = "timetable entry"
        verbose_name_plural = "timetable entries"

    def __str__(self):
        return f"{self.classroom} {self.get_day_display()} P{self.period}: {self.subject}"

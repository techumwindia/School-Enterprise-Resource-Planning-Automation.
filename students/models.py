from django.conf import settings
from django.db import models


class Student(models.Model):
    GENDER = [("M", "Male"), ("F", "Female"), ("O", "Other")]
    BLOOD = [(b, b) for b in ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]]

    admission_no = models.CharField(max_length=20, unique=True)
    emis_no = models.CharField("EMIS No.", max_length=30, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER)
    date_of_birth = models.DateField()
    blood_group = models.CharField(max_length=3, choices=BLOOD, blank=True)
    classroom = models.ForeignKey("academics.ClassRoom", null=True, on_delete=models.SET_NULL,
                                  related_name="students", verbose_name="class")
    roll_no = models.PositiveIntegerField(null=True, blank=True)
    admission_date = models.DateField()
    father_name = models.CharField(max_length=120, blank=True)
    mother_name = models.CharField(max_length=120, blank=True)
    guardian_phone = models.CharField(max_length=20)
    guardian_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    uses_transport = models.BooleanField("School bus", default=False)
    is_active = models.BooleanField(default=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name="student", help_text="Student login (optional)")
    parent_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="children", help_text="Parent login (optional)")

    class Meta:
        ordering = ["classroom__order", "classroom__section", "roll_no", "first_name"]

    def __str__(self):
        return f"{self.full_name} ({self.admission_no})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

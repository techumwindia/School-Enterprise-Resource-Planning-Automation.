from django.conf import settings
from django.db import models
from django.utils import timezone


class Notice(models.Model):
    AUDIENCE = [("all", "Everyone"), ("staff", "Staff only"), ("students", "Students & parents")]

    title = models.CharField(max_length=200)
    body = models.TextField()
    audience = models.CharField(max_length=10, choices=AUDIENCE, default="all")
    publish_date = models.DateField(default=timezone.localdate)
    is_pinned = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, editable=False)

    class Meta:
        ordering = ["-is_pinned", "-publish_date", "-id"]

    def __str__(self):
        return self.title


class Event(models.Model):
    title = models.CharField(max_length=200)
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_holiday = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.title} ({self.date})"


def notices_for(role):
    from accounts.models import Role
    qs = Notice.objects.filter(publish_date__lte=timezone.localdate())
    if role in (Role.STUDENT, Role.PARENT):
        qs = qs.filter(audience__in=["all", "students"])
    elif role in (Role.TEACHER, Role.ACCOUNTANT):
        qs = qs.filter(audience__in=["all", "staff"])
    return qs

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Role(models.TextChoices):
    ADMIN = "admin", "Administrator"
    TEACHER = "teacher", "Teacher"
    ACCOUNTANT = "accountant", "Accountant"
    STUDENT = "student", "Student"
    PARENT = "parent", "Parent"


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ADMIN)
    phone = models.CharField(max_length=20, blank=True)
    issued_password = models.CharField(
        max_length=128, blank=True,
        help_text="Password last set by the admin, shown so it can be given to the user. "
                  "Cleared when the user changes their own password.")

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance, defaults={"role": Role.ADMIN if instance.is_superuser else Role.STUDENT}
        )


def user_role(user):
    """Return the role string for a user ('' for anonymous)."""
    if not user.is_authenticated:
        return ""
    if user.is_superuser:
        return Role.ADMIN
    profile = getattr(user, "profile", None)
    return profile.role if profile else ""

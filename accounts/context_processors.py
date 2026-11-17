from django.conf import settings

from .models import user_role


def school(request):
    return {
        "SCHOOL_NAME": settings.SCHOOL_NAME,
        "SCHOOL_ADDRESS": settings.SCHOOL_ADDRESS,
        "SCHOOL_PHONE": settings.SCHOOL_PHONE,
        "SCHOOL_EMAIL": settings.SCHOOL_EMAIL,
        "user_role": user_role(request.user) if hasattr(request, "user") else "",
    }

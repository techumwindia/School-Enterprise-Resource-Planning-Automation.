"""Role-based access helpers used by every module."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .models import Role, user_role

STAFF_ROLES = (Role.ADMIN, Role.TEACHER, Role.ACCOUNTANT)


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if user_role(request.user) not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


class RoleRequiredMixin(LoginRequiredMixin):
    allowed_roles = (Role.ADMIN,)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and user_role(request.user) not in self.allowed_roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

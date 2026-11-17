from django import template
from django.db.models import Model

from accounts.models import user_role

register = template.Library()


@register.filter
def attr(obj, path):
    """Resolve a dotted attribute path; calls get_FOO_display / callables."""
    value = obj
    for part in path.split("."):
        if value is None:
            return ""
        display = getattr(value, f"get_{part}_display", None)
        value = display() if callable(display) else getattr(value, part, "")
        if callable(value) and not isinstance(value, Model):
            value = value()
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "" if value is None else value


@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None


@register.simple_tag(takes_context=True)
def role(context):
    return user_role(context["request"].user)


@register.filter
def add_class(field, css):
    return field.as_widget(attrs={"class": css})

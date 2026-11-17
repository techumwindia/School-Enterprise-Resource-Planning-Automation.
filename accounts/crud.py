"""
Small generic CRUD layer so each module only declares its model, form fields
and list columns. Templates: templates/crud/list.html, form.html, confirm_delete.html.
"""
from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.urls import path, reverse
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .models import Role, user_role
from .permissions import RoleRequiredMixin


class CrudConfig(RoleRequiredMixin):
    model = None
    title = ""
    columns = ()          # (label, "attr.path") pairs shown in the list
    search_fields = ()    # ORM lookups used by the search box
    list_filters = ()     # (param, "orm_field", choices_callable, label)
    url_prefix = ""       # e.g. "students:student"
    select_related = ()
    ordering = None
    extra_actions = ()    # (label, url_name, icon) extra buttons per row
    edit_roles = ()       # roles that see add/edit/delete buttons (default: allowed_roles)
    sort_map = {}         # column path -> ORM field(s) for columns that aren't plain model fields

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(title=self.title, columns=self.columns, url_prefix=self.url_prefix,
                   extra_actions=self.extra_actions, singular=self.model._meta.verbose_name.title(),
                   can_edit=user_role(self.request.user) in (self.edit_roles or self.allowed_roles))
        return ctx

    def get_success_url(self):
        return reverse(f"{self.url_prefix}_list")


def orm_path(model, path):
    """Turn a column path like 'class_teacher.name' into 'class_teacher__name' if it is a real field chain."""
    parts = []
    for part in path.split("."):
        try:
            field = model._meta.get_field(part)
        except FieldDoesNotExist:
            return None
        parts.append(part)
        model = getattr(field, "related_model", None) or model
    return "__".join(parts)


class CrudList(CrudConfig, ListView):
    template_name = "crud/list.html"
    paginate_by = 25

    def sort_fields(self, path):
        """ORM fields to order by for a column, or None if the column can't be sorted."""
        if path in self.sort_map:
            f = self.sort_map[path]
            return (f,) if isinstance(f, str) else tuple(f)
        f = orm_path(self.model, path)
        return (f,) if f else None

    def current_sort(self):
        """(column index, descending) from ?sort=3 or ?sort=-3, or (None, False)."""
        raw = self.request.GET.get("sort", "")
        desc = raw.startswith("-")
        try:
            idx = int(raw.lstrip("-"))
        except ValueError:
            return None, False
        if not (0 <= idx < len(self.columns)) or not self.sort_fields(self.columns[idx][1]):
            return None, False
        return idx, desc

    def get_queryset(self):
        qs = self.model.objects.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        idx, desc = self.current_sort()
        if idx is not None:
            fields = self.sort_fields(self.columns[idx][1])
            qs = qs.order_by(*[f"-{f}" if desc else f for f in fields], "-pk" if desc else "pk")
        elif self.ordering:
            qs = qs.order_by(*self.ordering)
        q = self.request.GET.get("q", "").strip()
        if q and self.search_fields:
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(cond)
        for param, field, _choices, _label in self.list_filters:
            val = self.request.GET.get(param)
            if val:
                qs = qs.filter(**{field: val})
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["searchable"] = bool(self.search_fields)
        ctx["filters"] = [
            {"param": p, "label": label, "choices": choices(), "value": self.request.GET.get(p, "")}
            for p, _f, choices, label in self.list_filters
        ]
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["querystring"] = params.urlencode()

        # Clickable column headings: click to sort A→Z, click again for Z→A
        params.pop("sort", None)
        base = params.urlencode()
        cur, desc = self.current_sort()
        headers = []
        for i, (label, path) in enumerate(self.columns):
            h = {"label": label, "sortable": bool(self.sort_fields(path)), "active": i == cur, "desc": desc}
            if h["sortable"]:
                nxt = f"-{i}" if (i == cur and not desc) else str(i)
                h["url"] = "?" + (base + "&" if base else "") + f"sort={nxt}"
            headers.append(h)
        ctx["headers"] = headers
        return ctx


def style_form(form):
    """Bootstrap classes + native date pickers for any Django form."""
    from django import forms as f
    for field in form.fields.values():
        w = field.widget
        if isinstance(field, f.DateField) and not isinstance(w, f.HiddenInput):
            field.widget = w = f.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        if isinstance(w, (f.CheckboxInput, f.CheckboxSelectMultiple, f.RadioSelect)):
            continue
        css = "form-select" if isinstance(w, f.Select) else "form-control"
        w.attrs["class"] = (w.attrs.get("class", "") + " " + css).strip()
    return form


class _SaveMixin:
    def get_form(self, form_class=None):
        return style_form(super().get_form(form_class))

    def form_valid(self, form):
        resp = super().form_valid(form)
        messages.success(self.request, f"{self.model._meta.verbose_name.title()} saved.")
        return resp


class CrudCreate(_SaveMixin, CrudConfig, CreateView):
    template_name = "crud/form.html"


class CrudUpdate(_SaveMixin, CrudConfig, UpdateView):
    template_name = "crud/form.html"


class CrudDelete(CrudConfig, DeleteView):
    template_name = "crud/confirm_delete.html"

    def form_valid(self, form):
        messages.success(self.request, f"{self.model._meta.verbose_name.title()} deleted.")
        return super().form_valid(form)


def make_crud(model, *, title, url_prefix, columns, fields=None, form_class=None, search_fields=(),
              list_filters=(), roles=(Role.ADMIN,), ordering=None, select_related=(), extra_actions=(),
              sort_map=None):
    """Build List/Create/Update/Delete view classes for a model in one call."""
    attrs = dict(model=model, title=title, url_prefix=url_prefix, columns=columns,
                 search_fields=search_fields, list_filters=list_filters, allowed_roles=roles,
                 ordering=ordering, select_related=select_related, extra_actions=extra_actions,
                 edit_roles=roles, sort_map=sort_map or {})
    form_attrs = dict(attrs, **({"form_class": form_class} if form_class else {"fields": fields}))
    name = model.__name__
    return (
        type(f"{name}List", (CrudList,), attrs),
        type(f"{name}Create", (CrudCreate,), form_attrs),
        type(f"{name}Update", (CrudUpdate,), form_attrs),
        type(f"{name}Delete", (CrudDelete,), attrs),
    )


def crud_urls(name, views, prefix=""):
    """Return the 4 standard URL patterns for a CRUD module."""
    List, Create, Update, Delete = views
    p = f"{prefix}/" if prefix else ""
    return [
        path(p, List.as_view(), name=f"{name}_list"),
        path(f"{p}add/", Create.as_view(), name=f"{name}_add"),
        path(f"{p}<int:pk>/edit/", Update.as_view(), name=f"{name}_edit"),
        path(f"{p}<int:pk>/delete/", Delete.as_view(), name=f"{name}_delete"),
    ]

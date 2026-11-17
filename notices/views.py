from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from accounts.crud import make_crud
from accounts.models import user_role

from .models import Event, Notice, notices_for


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ["title", "body", "audience", "publish_date", "is_pinned"]
        widgets = {"body": forms.Textarea(attrs={"rows": 6})}


NoticeViews = make_crud(
    Notice, title="Manage Notices", url_prefix="notices:notice", form_class=NoticeForm,
    columns=(("Title", "title"), ("Audience", "audience"), ("Date", "publish_date"), ("Pinned", "is_pinned")),
    search_fields=("title", "body"),
)


def _set_author(self, form):
    if not form.instance.created_by_id:
        form.instance.created_by = self.request.user
    return super(NoticeViews[1], self).form_valid(form)


NoticeViews[1].form_valid = _set_author

EventViews = make_crud(
    Event, title="Events & Holidays", url_prefix="notices:event",
    fields=["title", "date", "end_date", "is_holiday", "description"],
    columns=(("Event", "title"), ("Date", "date"), ("To", "end_date"), ("Holiday", "is_holiday")),
    search_fields=("title",),
)


@login_required
def board(request):
    today = timezone.localdate()
    return render(request, "notices/board.html", {
        "notices": notices_for(user_role(request.user))[:50],
        "events": Event.objects.filter(date__gte=today.replace(day=1))[:30],
        "today": today,
    })

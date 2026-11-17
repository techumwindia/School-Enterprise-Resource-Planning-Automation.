from django import forms
from django.contrib.auth.models import User

from .models import Role


class UserForm(forms.ModelForm):
    role = forms.ChoiceField(choices=Role.choices)
    phone = forms.CharField(required=False)
    password = forms.CharField(widget=forms.PasswordInput, required=False,
                               help_text="Leave blank to keep the current password (when editing).")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and hasattr(self.instance, "profile"):
            self.fields["role"].initial = self.instance.profile.role
            self.fields["phone"].initial = self.instance.profile.phone
        else:
            self.fields["password"].required = True
            self.fields["password"].help_text = ""

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data["password"]:
            user.set_password(self.cleaned_data["password"])
        user.save()
        profile = user.profile
        profile.role = self.cleaned_data["role"]
        profile.phone = self.cleaned_data["phone"]
        profile.save()
        return user

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from users.models import User


class UniqueEmailMixin(forms.Form):
    """Friendly duplicate-email error; the DB constraint is the backstop."""

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        taken = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)
        if email and taken.exists():
            raise forms.ValidationError("This email is already in use.")
        return email


class UserAdminCreationForm(UniqueEmailMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class UserAdminChangeForm(UniqueEmailMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    search_fields = ("username", "email")
    ordering = ("-id",)
    add_form = UserAdminCreationForm
    form = UserAdminChangeForm

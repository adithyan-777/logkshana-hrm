"""Login-username forms (self-service profile + admin employee edit).

The ``User`` table lives in the shared/public schema while both surfaces
run inside a tenant schema; the uniqueness query follows the same pattern
as ``employees.services`` (the DB unique constraint remains the backstop).
"""

from django import forms
from django.contrib.auth.validators import UnicodeUsernameValidator
from django_tenants.utils import get_public_schema_name, schema_context

from common.forms import apply_form_field_ui
from users.models import User


class UsernameUniquenessMixin:
    """Case-insensitive duplicate check for a ``username`` field.

    Subclasses return the pk of the user the submitted username belongs
    to (``None`` when there is no account yet) so keeping the current
    value passes. Case-insensitive because the friendly message should
    match how people read usernames, even though the DB constraint is
    case-sensitive.
    """

    def username_owner_pk(self):
        return None

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("Enter a username.")
        # Default message spells out the legal characters
        # (letters, numbers, @/./+/-/_).
        UnicodeUsernameValidator()(username)
        taken = User.objects.filter(username__iexact=username)
        owner_pk = self.username_owner_pk()
        if owner_pk is not None:
            taken = taken.exclude(pk=owner_pk)
        if taken.exists():
            raise forms.ValidationError("This username is already in use.")
        return username


class UsernameChangeForm(UsernameUniquenessMixin, forms.Form):
    """Self-service username change, confirmed with the current password."""

    username = forms.CharField(max_length=150, label="Username")
    current_password = forms.CharField(
        label="Current password",
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["username"].initial = user.username
        apply_form_field_ui(self)

    def username_owner_pk(self):
        return self.user.pk

    def clean_current_password(self):
        password = self.cleaned_data.get("current_password") or ""
        if not password or not self.user.check_password(password):
            raise forms.ValidationError(
                "Please enter your current password correctly."
            )
        return password

    def save(self):
        username = self.cleaned_data["username"]
        if username == self.user.username:
            return self.user
        self.user.username = username
        with schema_context(get_public_schema_name()):
            self.user.save(update_fields=["username"])
        return self.user

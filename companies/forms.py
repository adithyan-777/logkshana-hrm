from django import forms

from common.forms import apply_form_field_ui
from companies.models import Branch, Company, Device, DeviceType


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ["name", "code"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_form_field_ui(self)


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = ["serial_number", "name", "branch", "device_type", "is_active"]

    def __init__(self, *args, company: Company | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        # Branches are scoped to the current company; brands/models are
        # admin-managed — users only pick from the dropdown.
        if company is not None:
            self.fields["branch"].queryset = Branch.objects.filter(
                company=company
            ).order_by("name")
        else:
            self.fields["branch"].queryset = Branch.objects.order_by("name")
        self.fields["device_type"].queryset = DeviceType.objects.select_related(
            "brand"
        ).filter(is_active=True, brand__is_active=True).order_by(
            "brand__name", "model_name"
        )
        self.fields["device_type"].required = False
        self.fields["device_type"].label = "Brand / model"
        apply_form_field_ui(
            self,
            placeholders={
                "serial_number": "e.g. ZK-001",
                "name": "e.g. Main entrance clock",
            },
            empty_labels={
                "branch": "Select branch",
                "device_type": "Select brand / model",
            },
        )

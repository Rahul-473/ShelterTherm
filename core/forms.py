from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory

from .models import AssemblyLayer, ShelterDesign


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Required for account recovery.")

    class Meta:
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class ShelterDesignForm(forms.ModelForm):
    class Meta:
        model = ShelterDesign
        fields = [
            "name",
            "description",
            "location",
            "override_t_max",
            "override_t_min",
            "override_peak_solar",
            "override_wind_speed",
            "override_ground_temp",
            "length_m",
            "width_m",
            "height_m",
            "window_n_m2",
            "window_s_m2",
            "window_e_m2",
            "window_w_m2",
            "door_area_m2",
            "window_shgc",
            "day_ach",
            "night_ach",
            "occupants",
            "equipment_w",
            "comfort_model",
            "cool_roof_finish",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class AssemblyLayerForm(forms.ModelForm):
    class Meta:
        model = AssemblyLayer
        fields = ["element", "order", "material", "thickness_mm"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select form-select-sm")
            else:
                field.widget.attrs.setdefault("class", "form-control form-control-sm")


AssemblyLayerFormSet = inlineformset_factory(
    ShelterDesign,
    AssemblyLayer,
    form=AssemblyLayerForm,
    extra=3,
    can_delete=True,
)

"""
encounters/forms.py
===================
Forms related to encounters (mainly Vitals for now).
"""

from django import forms
from .models import Vitals


class VitalsForm(forms.ModelForm):
    """
    Form used by Nurse to record patient vitals.
    """
    class Meta:
        model = Vitals
        fields = [
            "height_cm",
            "weight_kg",
            "temperature_c",
            "blood_pressure",
            "pulse",
            "respiratory_rate",
            "spo2",
        ]
        widgets = {
            "height_cm": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 170",
                "step": "0.1"
            }),
            "weight_kg": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 65",
                "step": "0.1"
            }),
            "temperature_c": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 36.8",
                "step": "0.1"
            }),
            "blood_pressure": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 120/80"
            }),
            "pulse": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 78"
            }),
            "respiratory_rate": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 18"
            }),
            "spo2": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 98"
            }),
        }
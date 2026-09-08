"""
laboratory/forms.py
===================
Forms for sample collection and result entry.
"""

from django import forms
from .models import LabOrder, LabResult, LabOrderItem


class SampleCollectionForm(forms.ModelForm):
    """Mark sample as collected and assign sample number."""

    class Meta:
        model = LabOrder
        fields = ["sample_number"]
        widgets = {
            "sample_number": forms.TextInput(
                attrs={
                    "class": "form-control form-control-lg",
                    "placeholder": "e.g. LB-2026-000001",
                }
            ),
        }
        labels = {
            "sample_number": "Sample Number",
        }


class LabResultForm(forms.ModelForm):
    """Enter result value for a single lab test item."""

    class Meta:
        model = LabResult
        fields = ["value", "unit", "reference_range", "is_abnormal", "notes"]
        widgets = {
            "value": forms.TextInput(
                attrs={"class": "form-control form-control-lg", "placeholder": "Result value"}
            ),
            "unit": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. mg/dL, g/L"}
            ),
            "reference_range": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g. 3.5 - 5.5"}
            ),
            "is_abnormal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "Optional notes"}
            ),
        }
        labels = {
            "value": "Result Value",
            "unit": "Unit",
            "reference_range": "Reference Range",
            "is_abnormal": "Flag as Abnormal",
            "notes": "Notes",
        }
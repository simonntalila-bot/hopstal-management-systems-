"""
patients/forms.py
=================
Forms for patient registration and search.
"""

from django import forms
from .models import Patient


class PatientRegistrationForm(forms.ModelForm):
    """
    Form used by Receptionist to register a new patient.
    """
    class Meta:
        model = Patient
        fields = [
            "full_name",
            "date_of_birth",
            "gender",
            "phone",
            "address",
            "next_of_kin",
            "next_of_kin_phone",
            "insurance_number",
            "blood_group",
            "allergies",
            "chronic_conditions",
            "notes",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Full name of the patient"
            }),
            "date_of_birth": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date"
            }),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 0712 345 678"
            }),
            "address": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Home address"
            }),
            "next_of_kin": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Name of next of kin"
            }),
            "next_of_kin_phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Phone of next of kin"
            }),
            "insurance_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "NHIF / Insurance number (optional)"
            }),
            "blood_group": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. O+, A-, B+"
            }),
            "allergies": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Known allergies (very important)"
            }),
            "chronic_conditions": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "e.g. Diabetes, Hypertension"
            }),
            "notes": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Any extra notes"
            }),
        }


class PatientSearchForm(forms.Form):
    """
    Simple search form used on the patient list page.
    """
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Search by Patient ID, Name, Phone or Insurance..."
        })
    )
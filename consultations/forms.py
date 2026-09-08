"""
consultations/forms.py
======================
Forms for Doctor Consultation and e-Prescription.

Prescription.source:
  IN_HOUSE  – clinic pharmacy (stock checked)
  EXTERNAL  – printable PDF for outside pharmacy
"""

from django import forms

from pharmacy.models import Drug
from .models import Consultation, Prescription


class ConsultationForm(forms.ModelForm):
    """Doctor consultation notes and diagnosis."""

    class Meta:
        model = Consultation
        fields = [
            "symptoms",
            "findings",
            "diagnosis",
            "secondary_diagnosis",
            "treatment_plan",
            "follow_up_date",
            "notes",
        ]
        widgets = {
            "symptoms": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Patient's reported symptoms...",
                }
            ),
            "findings": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Clinical findings...",
                }
            ),
            "diagnosis": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Primary diagnosis...",
                }
            ),
            "secondary_diagnosis": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Secondary diagnosis (optional)...",
                }
            ),
            "treatment_plan": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Treatment plan and recommendations...",
                }
            ),
            "follow_up_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Additional notes...",
                }
            ),
        }


class PrescriptionForm(forms.ModelForm):
    """
    Add a medicine line to the current visit.
    Default source is IN_HOUSE so finish → Payment Pending (Pharmacy).
    """

    class Meta:
        model = Prescription
        fields = [
            "drug",
            "quantity",
            "dosage_instructions",
            "duration_days",
            "source",
            "external_notes",
        ]
        widgets = {
            "drug": forms.Select(attrs={"class": "form-select"}),
            "quantity": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "value": 1}
            ),
            "dosage_instructions": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. 1 tab TDS",
                }
            ),
            "duration_days": forms.NumberInput(
                attrs={"class": "form-control", "min": 1}
            ),
            "source": forms.Select(attrs={"class": "form-select"}),
            "external_notes": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Optional note on external Rx PDF",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Default: dispense at this pharmacy
        self.fields["source"].initial = Prescription.SOURCE_IN_HOUSE
        self.fields["source"].required = True
        self.fields["quantity"].initial = 1
        self.fields["external_notes"].required = False
        self.fields["duration_days"].required = False
        self.fields["dosage_instructions"].required = False

        # Clearer labels
        self.fields["source"].label = "Where to get medicine"
        self.fields["external_notes"].label = "External note (optional)"

        # Drug dropdown with live stock
        choices = [("", "---------")]
        qs = Drug.objects.filter(is_active=True).order_by("name")
        for d in qs:
            strength = getattr(d, "strength", "") or ""
            stock = getattr(d, "stock_quantity", 0) or 0
            label = f"{d.name} {strength}".strip()
            label = f"{label} — stock: {stock}"
            if stock <= 0:
                label += " (OUT OF STOCK)"
            elif getattr(d, "is_low_stock", False):
                label += " (LOW)"
            choices.append((d.pk, label))

        self.fields["drug"].choices = choices
        self.fields["drug"].queryset = qs

    def clean_source(self):
        source = self.cleaned_data.get("source") or Prescription.SOURCE_IN_HOUSE
        if source not in (
            Prescription.SOURCE_IN_HOUSE,
            Prescription.SOURCE_EXTERNAL,
        ):
            return Prescription.SOURCE_IN_HOUSE
        return source

    def clean_quantity(self):
        qty = self.cleaned_data.get("quantity") or 1
        if qty < 1:
            raise forms.ValidationError("Quantity must be at least 1.")
        return qty

    def clean(self):
        cleaned = super().clean()
        drug = cleaned.get("drug")
        qty = cleaned.get("quantity") or 1
        source = cleaned.get("source") or Prescription.SOURCE_IN_HOUSE
        cleaned["source"] = source

        if source == Prescription.SOURCE_IN_HOUSE and drug:
            stock = getattr(drug, "stock_quantity", 0) or 0
            if stock < qty:
                raise forms.ValidationError(
                    f"Not enough stock for {drug.name} "
                    f"(available {stock}, needed {qty}). "
                    f"Choose “External prescription (PDF)” or reduce quantity."
                )
            # Soft warning path: expired drugs still blocked if model has flag
            if getattr(drug, "is_expired", False):
                raise forms.ValidationError(
                    f"{drug.name} is expired and cannot be prescribed in-house. "
                    f"Use External prescription or another drug."
                )

        return cleaned
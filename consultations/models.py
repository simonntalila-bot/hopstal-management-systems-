"""
consultations/models.py
=======================
Consultation notes and prescriptions for CDMS.

Prescription.source:
  IN_HOUSE  – dispense at clinic pharmacy (stock checked)
  EXTERNAL  – printable PDF for outside pharmacy
"""

from django.conf import settings
from django.db import models

from core.models import BaseModel
from encounters.models import Encounter


class Consultation(BaseModel):
    """
    One consultation record per encounter (doctor notes / diagnosis).
    """
    encounter = models.OneToOneField(
        Encounter,
        on_delete=models.CASCADE,
        related_name="consultation",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations",
    )
    symptoms = models.TextField(blank=True)
    findings = models.TextField(blank=True)
    diagnosis = models.CharField(max_length=255, blank=True)
    secondary_diagnosis = models.CharField(max_length=255, blank=True)
    treatment_plan = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultations_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Consultation"
        verbose_name_plural = "Consultations"

    def __str__(self):
        return f"Consultation #{self.pk} – {self.encounter}"


class Prescription(BaseModel):
    """
    Medicine line for a visit.

    IN_HOUSE  → stock must be available; goes to Pharmacy after payment.
    EXTERNAL  → no stock check; printable PDF; not sent to clinic pharmacy.
    """
    SOURCE_IN_HOUSE = "IN_HOUSE"
    SOURCE_EXTERNAL = "EXTERNAL"
    SOURCE_CHOICES = [
        (SOURCE_IN_HOUSE, "Dispense at this pharmacy"),
        (SOURCE_EXTERNAL, "External prescription (PDF)"),
    ]

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions",
    )
    drug = models.ForeignKey(
        "pharmacy.Drug",
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )
    quantity = models.PositiveIntegerField(default=1)
    dosage_instructions = models.CharField(max_length=255, blank=True)
    duration_days = models.PositiveIntegerField(null=True, blank=True)

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_IN_HOUSE,
        db_index=True,
        help_text="In-house uses clinic stock; External is for outside pharmacies.",
    )
    external_notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional note printed on external prescription.",
    )
    is_dispensed = models.BooleanField(
        default=False,
        help_text="Set when clinic pharmacy has dispensed this line.",
    )

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions_written",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions_created",
    )

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Prescription"
        verbose_name_plural = "Prescriptions"

    def __str__(self):
        where = "external" if self.source == self.SOURCE_EXTERNAL else "in-house"
        return f"{self.drug} x{self.quantity} ({where})"

    @property
    def is_external(self):
        return self.source == self.SOURCE_EXTERNAL

    @property
    def is_in_house(self):
        return self.source == self.SOURCE_IN_HOUSE
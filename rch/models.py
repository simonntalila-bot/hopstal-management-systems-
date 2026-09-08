"""
rch/models.py
=============
Reproductive & Child Health – Phase A

- RCHClientProfile (mother/child obstetric & link data)
- RCHVisit (typed visit linked to Encounter)
- ANCRecord, Under5Record, ImmunizationRecord
- FamilyPlanningRecord, PNCRecord
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from encounters.models import Encounter
from patients.models import Patient


class RCHClientProfile(BaseModel):
    """
    Extra RCH data for a patient (mother or child).
    Created on first RCH contact if missing.
    """
    CLIENT_MOTHER = "MOTHER"
    CLIENT_CHILD = "CHILD"
    CLIENT_CHOICES = [
        (CLIENT_MOTHER, "Mother / woman of reproductive age"),
        (CLIENT_CHILD, "Child / under-5"),
    ]

    patient = models.OneToOneField(
        Patient,
        on_delete=models.CASCADE,
        related_name="rch_profile",
    )
    client_type = models.CharField(
        max_length=10,
        choices=CLIENT_CHOICES,
        default=CLIENT_MOTHER,
        db_index=True,
    )

    # Obstetric history (mothers)
    gravida = models.PositiveSmallIntegerField(null=True, blank=True)
    para = models.PositiveSmallIntegerField(null=True, blank=True)
    abortions = models.PositiveSmallIntegerField(null=True, blank=True, default=0)
    living_children = models.PositiveSmallIntegerField(null=True, blank=True)

    # Child → mother link (optional)
    mother = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rch_children",
        help_text="Mother patient record for this child",
    )

    blood_group = models.CharField(max_length=5, blank=True)
    hiv_status = models.CharField(
        max_length=20,
        blank=True,
        help_text="Unknown / Negative / Positive / Declined",
    )
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rch_profiles_created",
    )

    class Meta:
        verbose_name = "RCH client profile"
        verbose_name_plural = "RCH client profiles"

    def __str__(self):
        return f"RCH profile – {self.patient}"


class RCHVisit(BaseModel):
    """
    One RCH service episode, linked to a paid CDMS Encounter.
    """
    ANC = "ANC"
    PNC = "PNC"
    UNDER5 = "UNDER5"
    IMMUNIZATION = "IMMUNIZATION"
    FP = "FP"
    NUTRITION = "NUTRITION"
    OTHER = "OTHER"

    SERVICE_CHOICES = [
        (ANC, "Antenatal care (ANC)"),
        (PNC, "Postnatal care (PNC)"),
        (UNDER5, "Under-5 / child health"),
        (IMMUNIZATION, "Immunization"),
        (FP, "Family planning"),
        (NUTRITION, "Nutrition"),
        (OTHER, "Other RCH"),
    ]

    encounter = models.OneToOneField(
        Encounter,
        on_delete=models.CASCADE,
        related_name="rch_visit",
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="rch_visits",
    )
    service_type = models.CharField(
        max_length=20,
        choices=SERVICE_CHOICES,
        db_index=True,
    )
    visit_date = models.DateField(default=timezone.localdate, db_index=True)
    attended_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rch_visits_attended",
    )
    next_appointment = models.DateField(null=True, blank=True, db_index=True)
    clinical_notes = models.TextField(blank=True)
    is_high_risk = models.BooleanField(default=False, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rch_visits_created",
    )

    class Meta:
        ordering = ["-visit_date", "-created_at"]
        verbose_name = "RCH visit"
        verbose_name_plural = "RCH visits"

    def __str__(self):
        return f"{self.get_service_type_display()} – {self.patient} ({self.visit_date})"


class ANCRecord(BaseModel):
    """Antenatal care details for an ANC RCH visit."""

    rch_visit = models.OneToOneField(
        RCHVisit,
        on_delete=models.CASCADE,
        related_name="anc",
    )
    lmp = models.DateField(
        null=True,
        blank=True,
        help_text="Last menstrual period",
    )
    edd = models.DateField(
        null=True,
        blank=True,
        help_text="Expected date of delivery",
    )
    gestational_age_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    anc_visit_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="e.g. 1st, 2nd, 4th ANC visit",
    )

    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    fetal_heart_rate = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Beats per minute",
    )

    # Fetal / abdominal measurements
    fundal_height_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Symphysis–fundal height (cm)",
    )
    abdominal_circumference_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Maternal abdominal circumference (cm)",
    )
    expected_fetal_weight_g = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Estimated / expected fetal weight in grams",
    )
    expected_fetal_length_cm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Expected fetal length / height (cm), if recorded",
    )

    risk_factors = models.TextField(blank=True)
    supplements = models.CharField(
        max_length=255,
        blank=True,
        help_text="e.g. Fe/FA, SP, calcium, ITN issued",
    )
    lab_notes = models.TextField(blank=True)
    ultrasound_notes = models.TextField(blank=True)
    plan = models.TextField(blank=True)

    class Meta:
        verbose_name = "ANC record"
        verbose_name_plural = "ANC records"

    def __str__(self):
        return f"ANC – RCH visit {self.rch_visit_id}"


class Under5Record(BaseModel):
    """Under-5 / child health visit details."""

    rch_visit = models.OneToOneField(
        RCHVisit,
        on_delete=models.CASCADE,
        related_name="under5",
    )
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    muac_cm = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Mid-upper arm circumference (cm)",
    )
    temperature_c = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    nutrition_status = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g. Normal / MAM / SAM",
    )
    development_notes = models.TextField(blank=True)
    diagnosis = models.CharField(max_length=255, blank=True)
    treatment = models.TextField(blank=True)

    class Meta:
        verbose_name = "Under-5 record"
        verbose_name_plural = "Under-5 records"

    def __str__(self):
        return f"Under-5 – RCH visit {self.rch_visit_id}"


class ImmunizationRecord(BaseModel):
    """One vaccine dose administered (several allowed per visit)."""

    VACCINE_CHOICES = [
        ("BCG", "BCG"),
        ("OPV0", "OPV-0"),
        ("OPV1", "OPV-1"),
        ("OPV2", "OPV-2"),
        ("OPV3", "OPV-3"),
        ("PENTA1", "Penta-1"),
        ("PENTA2", "Penta-2"),
        ("PENTA3", "Penta-3"),
        ("PCV1", "PCV-1"),
        ("PCV2", "PCV-2"),
        ("PCV3", "PCV-3"),
        ("ROTA1", "Rota-1"),
        ("ROTA2", "Rota-2"),
        ("ROTA3", "Rota-3"),
        ("IPV", "IPV"),
        ("MEASLES1", "Measles-1"),
        ("MEASLES2", "Measles-2"),
        ("TT", "TT / Td"),
        ("HPV", "HPV"),
        ("OTHER", "Other"),
    ]

    rch_visit = models.ForeignKey(
        RCHVisit,
        on_delete=models.CASCADE,
        related_name="immunizations",
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="immunizations",
    )
    vaccine = models.CharField(max_length=20, choices=VACCINE_CHOICES, db_index=True)
    vaccine_other = models.CharField(
        max_length=100,
        blank=True,
        help_text="If vaccine=OTHER",
    )
    dose_date = models.DateField(default=timezone.localdate, db_index=True)
    next_due = models.DateField(null=True, blank=True)
    batch_number = models.CharField(max_length=50, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="immunizations_created",
    )

    class Meta:
        ordering = ["-dose_date", "-created_at"]
        verbose_name = "Immunization record"
        verbose_name_plural = "Immunization records"

    def __str__(self):
        label = (
            self.vaccine_other
            if self.vaccine == "OTHER" and self.vaccine_other
            else self.vaccine
        )
        return f"{label} – {self.patient} ({self.dose_date})"


class FamilyPlanningRecord(BaseModel):
    """Family planning counselling / method for an FP visit."""

    METHOD_CHOICES = [
        ("PILL", "Oral pill"),
        ("INJECTABLE", "Injectable"),
        ("IMPLANT", "Implant"),
        ("IUD", "IUD"),
        ("CONDOM", "Condom"),
        ("NATURAL", "Natural / LAM"),
        ("STERILIZATION", "Sterilization"),
        ("OTHER", "Other"),
    ]

    rch_visit = models.OneToOneField(
        RCHVisit,
        on_delete=models.CASCADE,
        related_name="fp",
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, blank=True)
    method_provided = models.BooleanField(
        default=False,
        help_text="Method was issued/provided this visit",
    )
    previous_method = models.CharField(max_length=50, blank=True)
    side_effects = models.TextField(blank=True)
    counselling_notes = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Family planning record"
        verbose_name_plural = "Family planning records"

    def __str__(self):
        return f"FP – RCH visit {self.rch_visit_id}"


class PNCRecord(BaseModel):
    """Postnatal care – mother and baby (Phase A simplified)."""

    rch_visit = models.OneToOneField(
        RCHVisit,
        on_delete=models.CASCADE,
        related_name="pnc",
    )
    days_postpartum = models.PositiveSmallIntegerField(null=True, blank=True)
    mother_bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    mother_bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    mother_condition = models.TextField(blank=True)
    bleeding = models.CharField(max_length=50, blank=True)
    breastfeeding = models.CharField(max_length=50, blank=True)
    baby_condition = models.TextField(blank=True)
    baby_weight_kg = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    counselling = models.TextField(blank=True)

    class Meta:
        verbose_name = "PNC record"
        verbose_name_plural = "PNC records"

    def __str__(self):
        return f"PNC – RCH visit {self.rch_visit_id}"
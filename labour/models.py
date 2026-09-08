"""
labour/models.py
================
Labour & Delivery – Phase A

LabourCase (admission + case header)
LabourAssessment
PartographEntry
MaternalObservation / FetalObservation
LabourMedication
DeliveryRecord
NewbornRecord (twins+)
LabourComplication
PostDeliveryCare
LabourReferral
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from encounters.models import Encounter
from patients.models import Patient


class LabourCase(BaseModel):
    """
    One labour admission episode for a mother, linked to Encounter.
    """
    STATUS_ACTIVE = "ACTIVE"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_REFERRED = "REFERRED"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "In labour / admitted"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_REFERRED, "Referred out"),
        (STATUS_CLOSED, "Closed"),
    ]

    encounter = models.OneToOneField(
        Encounter,
        on_delete=models.CASCADE,
        related_name="labour_case",
    )
    mother = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="labour_cases",
    )

    admission_at = models.DateTimeField(default=timezone.now, db_index=True)
    gestational_age_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    gravida = models.PositiveSmallIntegerField(null=True, blank=True)
    para = models.PositiveSmallIntegerField(null=True, blank=True)
    lmp = models.DateField(null=True, blank=True)
    edd = models.DateField(null=True, blank=True)

    presenting_complaint = models.TextField(blank=True)
    labour_onset_at = models.DateTimeField(null=True, blank=True)
    membrane_status = models.CharField(
        max_length=50, blank=True,
        help_text="Intact / Ruptured / Artificial rupture",
    )
    liquor = models.CharField(max_length=50, blank=True)
    contractions = models.CharField(max_length=100, blank=True)
    cervical_dilatation_cm = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    is_high_risk = models.BooleanField(default=False)
    previous_cs = models.BooleanField(default=False)
    previous_delivery_notes = models.TextField(blank=True)

    initial_bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    initial_bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    initial_pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    initial_temperature = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True
    )
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="labour_admissions",
    )
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="labour_cases_created",
    )

    class Meta:
        ordering = ["-admission_at"]
        verbose_name = "Labour case"
        verbose_name_plural = "Labour cases"

    def __str__(self):
        return f"Labour – {self.mother} ({self.admission_at:%Y-%m-%d %H:%M})"


class LabourAssessment(BaseModel):
    """Vaginal / labour examination snapshot."""

    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="assessments"
    )
    assessed_at = models.DateTimeField(default=timezone.now, db_index=True)
    cervical_dilatation_cm = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    effacement = models.CharField(max_length=30, blank=True)
    station = models.CharField(max_length=20, blank=True)
    presentation = models.CharField(max_length=50, blank=True)
    position = models.CharField(max_length=50, blank=True)
    membrane_status = models.CharField(max_length=50, blank=True)
    liquor = models.CharField(max_length=50, blank=True)
    contraction_frequency = models.CharField(max_length=50, blank=True)
    contraction_duration = models.CharField(max_length=50, blank=True)
    pelvic_assessment = models.TextField(blank=True)
    maternal_condition = models.TextField(blank=True)
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="labour_assessments",
    )

    class Meta:
        ordering = ["-assessed_at"]

    def __str__(self):
        return f"Assessment {self.assessed_at} – case {self.labour_case_id}"


class PartographEntry(BaseModel):
    """
    One timed partograph row. Chart plotted later from these points.
    """
    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="partograph_entries"
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)

    cervical_dilatation_cm = models.DecimalField(
        max_digits=3, decimal_places=1, null=True, blank=True
    )
    descent_of_head = models.CharField(max_length=20, blank=True)
    fetal_heart_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    contractions = models.CharField(max_length=80, blank=True)

    maternal_pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    temperature = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )

    urine_output_ml = models.PositiveIntegerField(null=True, blank=True)
    urine_protein = models.CharField(max_length=20, blank=True)
    urine_ketones = models.CharField(max_length=20, blank=True)

    oxytocin = models.CharField(max_length=100, blank=True)
    iv_fluids = models.CharField(max_length=100, blank=True)
    other_interventions = models.CharField(max_length=255, blank=True)
    alert_flag = models.BooleanField(
        default=False,
        help_text="Staff-marked abnormal observation for review",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partograph_entries",
    )

    class Meta:
        ordering = ["recorded_at"]
        verbose_name = "Partograph entry"
        verbose_name_plural = "Partograph entries"

    def __str__(self):
        return f"Partograph {self.recorded_at} – case {self.labour_case_id}"


class MaternalObservation(BaseModel):
    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="maternal_obs"
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    respiratory_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    temperature = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    spo2 = models.PositiveSmallIntegerField(null=True, blank=True)
    pain_score = models.PositiveSmallIntegerField(null=True, blank=True)
    consciousness = models.CharField(max_length=50, blank=True)
    urine_output_ml = models.PositiveIntegerField(null=True, blank=True)
    bleeding = models.CharField(max_length=50, blank=True)
    general_condition = models.TextField(blank=True)
    alert_flag = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maternal_obs_recorded",
    )

    class Meta:
        ordering = ["-recorded_at"]


class FetalObservation(BaseModel):
    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="fetal_obs"
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    fetal_heart_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    fetal_movement = models.CharField(max_length=50, blank=True)
    presentation = models.CharField(max_length=50, blank=True)
    position = models.CharField(max_length=50, blank=True)
    station = models.CharField(max_length=20, blank=True)
    liquor = models.CharField(max_length=50, blank=True)
    distress_notes = models.TextField(blank=True)
    alert_flag = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fetal_obs_recorded",
    )

    class Meta:
        ordering = ["-recorded_at"]


class LabourMedication(BaseModel):
    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="medications"
    )
    given_at = models.DateTimeField(default=timezone.now)
    drug_name = models.CharField(max_length=150)
    dose = models.CharField(max_length=80, blank=True)
    route = models.CharField(max_length=40, blank=True)
    indication = models.CharField(max_length=255, blank=True)
    administered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="labour_meds_given",
    )

    class Meta:
        ordering = ["-given_at"]


class DeliveryRecord(BaseModel):
    MODE_SVD = "SVD"
    MODE_ASSISTED = "ASSISTED"
    MODE_CS = "CS"
    MODE_OTHER = "OTHER"
    MODE_CHOICES = [
        (MODE_SVD, "Spontaneous vaginal delivery"),
        (MODE_ASSISTED, "Assisted vaginal delivery"),
        (MODE_CS, "Caesarean section"),
        (MODE_OTHER, "Other"),
    ]

    labour_case = models.OneToOneField(
        LabourCase, on_delete=models.CASCADE, related_name="delivery"
    )
    delivered_at = models.DateTimeField(default=timezone.now, db_index=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_SVD)
    indication = models.TextField(blank=True)
    presentation = models.CharField(max_length=50, blank=True)
    position = models.CharField(max_length=50, blank=True)
    placenta_delivered_at = models.DateTimeField(null=True, blank=True)
    placenta_complete = models.BooleanField(null=True, blank=True)
    estimated_blood_loss_ml = models.PositiveIntegerField(null=True, blank=True)
    perineum = models.CharField(max_length=100, blank=True)
    episiotomy = models.BooleanField(default=False)
    suturing = models.CharField(max_length=100, blank=True)
    delivery_notes = models.TextField(blank=True)
    conducted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deliveries_conducted",
    )

    def __str__(self):
        return f"Delivery {self.delivered_at} – case {self.labour_case_id}"


class NewbornRecord(BaseModel):
    """
    One baby from a delivery. Twins = two rows.
    Optionally creates/links a Patient record for the child.
    """
    SEX_M = "M"
    SEX_F = "F"
    SEX_U = "U"
    SEX_CHOICES = [(SEX_M, "Male"), (SEX_F, "Female"), (SEX_U, "Unknown")]

    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="newborns"
    )
    delivery = models.ForeignKey(
        DeliveryRecord,
        on_delete=models.CASCADE,
        related_name="newborns",
        null=True,
        blank=True,
    )
    mother = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="newborns_delivered",
    )
    # Optional separate patient file for the baby
    baby_patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="as_newborn_record",
    )

    birth_order = models.PositiveSmallIntegerField(default=1)
    born_at = models.DateTimeField(default=timezone.now)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, default=SEX_U)
    birth_weight_kg = models.DecimalField(
        max_digits=5, decimal_places=3, null=True, blank=True
    )
    length_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    head_circumference_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    apgar_1 = models.PositiveSmallIntegerField(null=True, blank=True)
    apgar_5 = models.PositiveSmallIntegerField(null=True, blank=True)
    apgar_10 = models.PositiveSmallIntegerField(null=True, blank=True)
    gestational_age_weeks = models.PositiveSmallIntegerField(null=True, blank=True)
    birth_status = models.CharField(
        max_length=40, blank=True,
        help_text="Live birth / Stillbirth / etc.",
    )
    resuscitation = models.BooleanField(default=False)
    condition_notes = models.TextField(blank=True)
    breastfeeding_initiated = models.BooleanField(null=True, blank=True)
    interventions = models.TextField(blank=True)

    class Meta:
        ordering = ["birth_order", "born_at"]

    def __str__(self):
        return f"Newborn #{self.birth_order} – mother {self.mother_id}"


class LabourComplication(BaseModel):
    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="complications"
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    category = models.CharField(
        max_length=80, blank=True,
        help_text="e.g. PPH, obstructed labour, fetal distress",
    )
    description = models.TextField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="labour_complications_recorded",
    )

    class Meta:
        ordering = ["-recorded_at"]


class PostDeliveryCare(BaseModel):
    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="post_delivery_care"
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    # Mother
    mother_bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    mother_bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    mother_pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    bleeding = models.CharField(max_length=50, blank=True)
    uterus = models.CharField(max_length=80, blank=True)
    pain = models.CharField(max_length=50, blank=True)
    perineum_wound = models.CharField(max_length=100, blank=True)
    mother_medications = models.TextField(blank=True)
    breastfeeding = models.CharField(max_length=50, blank=True)
    mother_condition = models.TextField(blank=True)
    # Baby summary (detail stays on NewbornRecord)
    baby_feeding = models.CharField(max_length=50, blank=True)
    baby_temperature = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    baby_notes = models.TextField(blank=True)
    disposition = models.CharField(
        max_length=80, blank=True,
        help_text="e.g. Ward / Discharge / NICU / Referral",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="post_delivery_recorded",
    )

    class Meta:
        ordering = ["-recorded_at"]


class LabourReferral(BaseModel):
    labour_case = models.ForeignKey(
        LabourCase, on_delete=models.CASCADE, related_name="referrals"
    )
    referred_at = models.DateTimeField(default=timezone.now)
    reason = models.TextField()
    receiving_facility = models.CharField(max_length=200, blank=True)
    maternal_condition = models.TextField(blank=True)
    fetal_newborn_condition = models.TextField(blank=True)
    treatment_given = models.TextField(blank=True)
    transport = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="labour_referrals_made",
    )

    class Meta:
        ordering = ["-referred_at"]
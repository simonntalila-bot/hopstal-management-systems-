"""
encounters/models.py
====================
Visit (Encounter) engine for Argentina Dispensary (CDMS).

Rules:
- Strict pay-before-service for cash / mobile money patients
- NHIF beneficiaries (patient.is_nhif) skip payment and go straight
  to the target department
- One patient → many visits
- Status PAYMENT_PENDING blocks department entry until paid (non-NHIF)
- Vitals can be recorded by Reception or Doctor per visit
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from patients.models import Patient


class EncounterManager(models.Manager):
    def open(self):
        return self.exclude(status__in=["COMPLETED", "CANCELLED"])

    def payment_pending(self):
        return self.filter(status="PAYMENT_PENDING")

    def for_department(self, department):
        return self.filter(
            current_department=department,
            status="IN_PROGRESS",
        ).order_by("created_at")


class Encounter(BaseModel):
    """
    One clinic visit. Central object for all departments.
    """

    DEPARTMENT_CHOICES = [
        ("RECEPTION", "Reception"),
        ("DOCTOR", "Doctor"),
        ("LAB", "Laboratory"),
        ("ULTRASOUND", "Ultrasound"),
        ("INJECTION", "Injection Room"),
        ("MINOR_SURGERY", "Minor Surgery"),
        ("RCH", "RCH"),
        ("LABOUR_WARD", "Labour Ward"),
        ("PHARMACY", "Pharmacy"),
    ]

    STATUS_CHOICES = [
        ("REGISTERED", "Registered"),
        ("PAYMENT_PENDING", "Payment Pending"),
        ("IN_PROGRESS", "In Progress"),
        ("RESULTS_READY", "Results Ready"),
        ("PRESCRIPTION_WRITTEN", "Prescription Written"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    VALID_TRANSITIONS = {
        "REGISTERED": {"PAYMENT_PENDING", "IN_PROGRESS", "CANCELLED"},
        "PAYMENT_PENDING": {"IN_PROGRESS", "CANCELLED"},
        "IN_PROGRESS": {
            "PAYMENT_PENDING",
            "RESULTS_READY",
            "PRESCRIPTION_WRITTEN",
            "COMPLETED",
            "CANCELLED",
        },
        "RESULTS_READY": {
            "IN_PROGRESS",
            "PAYMENT_PENDING",
            "COMPLETED",
            "CANCELLED",
        },
        "PRESCRIPTION_WRITTEN": {"PAYMENT_PENDING", "COMPLETED", "CANCELLED"},
        "COMPLETED": set(),
        "CANCELLED": set(),
    }

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="encounters",
    )
    visit_type = models.CharField(max_length=20, default="OPD")
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default="REGISTERED",
        db_index=True,
    )
    current_department = models.CharField(
        max_length=20,
        choices=DEPARTMENT_CHOICES,
        default="RECEPTION",
        db_index=True,
    )
    chief_complaint = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    nhif_auth_code = models.CharField(max_length=50, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = EncounterManager()

    class Meta:
        verbose_name = "Visit / Encounter"
        verbose_name_plural = "Visits / Encounters"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "current_department"]),
            models.Index(fields=["patient", "status"]),
        ]

    def __str__(self):
        return f"{self.patient.patient_id} → {self.current_department} ({self.status})"

    @property
    def is_nhif_patient(self):
        return bool(getattr(self.patient, "is_nhif", False))

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status, user=None, department=None, note=""):
        department_only = (
            new_status == self.status
            and department is not None
            and department != self.current_department
        )

        if new_status == self.status and department is None:
            return

        if not department_only and not self.can_transition_to(new_status):
            raise ValidationError(
                f"Cannot move from {self.status} to {new_status}."
            )

        old_status = self.status
        old_dept = self.current_department

        self.status = new_status
        if department:
            self.current_department = department

        if new_status in ("COMPLETED", "CANCELLED"):
            self.closed_at = timezone.now()

        self.save()

        VisitLog.objects.create(
            encounter=self,
            from_status=old_status,
            to_status=self.status,
            from_department=old_dept,
            to_department=self.current_department,
            performed_by=user,
            note=note or f"Status changed to {self.status}",
        )

    def release_to_department(self, department, user=None, note=""):
        old_status = self.status
        old_dept = self.current_department
        self.status = "IN_PROGRESS"
        self.current_department = department
        if self.closed_at:
            self.closed_at = None
        self.save(
            update_fields=[
                "status",
                "current_department",
                "closed_at",
                "updated_at",
            ]
        )
        VisitLog.objects.create(
            encounter=self,
            from_status=old_status,
            to_status="IN_PROGRESS",
            from_department=old_dept,
            to_department=department,
            performed_by=user,
            note=note or f"Released to {department} (no payment)",
        )

    def mark_payment_pending(self, target_department, user=None):
        if self.is_nhif_patient:
            self.release_to_department(
                target_department,
                user=user,
                note=(
                    f"NHIF beneficiary – payment bypassed; "
                    f"released to {target_department}"
                ),
            )
            return

        self.transition_to(
            "PAYMENT_PENDING",
            user=user,
            department=target_department,
            note=f"Awaiting payment for {target_department}",
        )

    def mark_paid_and_release(self, user=None, note=""):
        if self.status != "PAYMENT_PENDING":
            if self.status == "IN_PROGRESS":
                return
            raise ValidationError("Visit is not waiting for payment.")

        self.transition_to(
            "IN_PROGRESS",
            user=user,
            department=self.current_department,
            note=note or f"Paid – released to {self.current_department}",
        )


class VisitLog(BaseModel):
    """Append-only history of status and department changes."""

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    from_department = models.CharField(max_length=20, blank=True)
    to_department = models.CharField(max_length=20, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_logs_performed",
    )
    note = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Visit Log"
        verbose_name_plural = "Visit Logs"

    def __str__(self):
        return f"{self.encounter_id}: {self.from_status} → {self.to_status}"


class Vitals(BaseModel):
    """
    Vitals for one visit. Recorded by Reception and/or Doctor.
    Multiple rows per encounter are allowed (history); latest is shown in UI.
    """

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="vitals",
    )
    height_cm = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    weight_kg = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True
    )
    temperature_c = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    blood_pressure = models.CharField(
        max_length=15, blank=True, help_text="e.g. 120/80"
    )
    pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    respiratory_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    spo2 = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Oxygen saturation %"
    )
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vitals_recorded",
    )
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Vitals"
        verbose_name_plural = "Vitals"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Vitals for {self.encounter} @ {self.recorded_at:%Y-%m-%d %H:%M}"


class Payment(BaseModel):
    """
    Payment log for pay-before-service (CDMS).
    Unique related_names avoid clash with billing.Payment.
    """

    METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("NHIF", "NHIF (no cash)"),
    ]

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.PROTECT,
        related_name="visit_payments",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Amount paid in TZS (0 for NHIF release)",
    )
    method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default="CASH",
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Mobile Money transaction ID or NHIF auth code",
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_payments_received",
    )
    received_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visit_payments_created",
    )

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Visit Payment"
        verbose_name_plural = "Visit Payments"

    def __str__(self):
        return f"TZS {self.amount} ({self.method}) – Visit #{self.encounter_id}"
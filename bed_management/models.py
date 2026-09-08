from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from encounters.models import Encounter


class Ward(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Ward"
        verbose_name_plural = "Wards"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def occupied_count(self):
        return self.beds.filter(status="OCCUPIED").count()

    @property
    def available_count(self):
        return self.beds.filter(status="AVAILABLE").count()


class Bed(BaseModel):
    STATUS_CHOICES = [
        ("AVAILABLE", "Available"),
        ("OCCUPIED", "Occupied"),
        ("MAINTENANCE", "Under Maintenance"),
        ("RESERVED", "Reserved"),
    ]

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    bed_number = models.CharField(max_length=20)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="AVAILABLE", db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Bed"
        verbose_name_plural = "Beds"
        unique_together = [("ward", "bed_number")]
        ordering = ["ward__name", "bed_number"]

    def __str__(self):
        return f"{self.ward.name} – Bed {self.bed_number} ({self.status})"

    def is_available_for_admission(self):
        return self.status == "AVAILABLE"


class Admission(BaseModel):
    encounter = models.OneToOneField(Encounter, on_delete=models.PROTECT, related_name="admission")
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="admissions")
    admitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="admissions_made"
    )
    admitted_at = models.DateTimeField(default=timezone.now)
    discharged_at = models.DateTimeField(null=True, blank=True)
    discharge_notes = models.TextField(blank=True)
    nursing_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Admission"
        verbose_name_plural = "Admissions"
        ordering = ["-admitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bed"],
                condition=models.Q(discharged_at__isnull=True),
                name="one_open_admission_per_bed",
            )
        ]

    def __str__(self):
        return f"Admission {self.encounter.patient} → {self.bed}"

    def clean(self):
        if self.bed_id and self.discharged_at is None:
            conflict = Admission.objects.filter(bed=self.bed, discharged_at__isnull=True).exclude(pk=self.pk).exists()
            if conflict:
                raise ValidationError(f"Bed {self.bed} already has an open admission.")
            if self.bed.status not in ("AVAILABLE", "RESERVED") and not self.pk:
                raise ValidationError(f"Bed {self.bed} is not available (current status: {self.bed.status}).")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.full_clean()
        super().save(*args, **kwargs)
        if is_new:
            self.bed.status = "OCCUPIED"
            self.bed.save(update_fields=["status", "updated_at"])
            if self.encounter.status not in ("ADMITTED", "IN_WARD"):
                self.encounter.status = "ADMITTED"
                self.encounter.visit_type = "IPD"
                self.encounter.save(update_fields=["status", "visit_type", "updated_at"])

    def discharge(self, user=None, notes=""):
        if self.discharged_at:
            raise ValidationError("Already discharged.")
        self.discharged_at = timezone.now()
        self.discharge_notes = notes
        self.save(update_fields=["discharged_at", "discharge_notes", "updated_at"])
        self.bed.status = "AVAILABLE"
        self.bed.save(update_fields=["status", "updated_at"])
        self.encounter.transition_to("DISCHARGED", user=user)
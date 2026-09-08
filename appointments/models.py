from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from patients.models import Patient


class Appointment(BaseModel):
    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("CHECKED_IN", "Checked In"),
        ("NO_SHOW", "No Show"),
        ("CANCELLED", "Cancelled"),
        ("COMPLETED", "Completed"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="appointments")
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="appointments",
        limit_choices_to={"staff_profile__role": "DOCTOR"},
    )
    department = models.CharField(max_length=100, blank=True)
    scheduled_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="SCHEDULED", db_index=True)
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Appointment"
        verbose_name_plural = "Appointments"
        ordering = ["scheduled_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "scheduled_at"],
                name="unique_doctor_slot",
                condition=models.Q(status__in=["SCHEDULED", "CHECKED_IN"]),
            )
        ]
        indexes = [models.Index(fields=["scheduled_at", "status"])]

    def __str__(self):
        return f"{self.patient} with Dr. {self.doctor} @ {self.scheduled_at:%Y-%m-%d %H:%M}"

    def clean(self):
        if self.scheduled_at and self.doctor_id:
            conflict = (
                Appointment.objects.filter(
                    doctor=self.doctor,
                    scheduled_at=self.scheduled_at,
                    status__in=["SCHEDULED", "CHECKED_IN"],
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if conflict:
                raise ValidationError("This doctor already has an appointment at the selected time.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def check_in(self, user=None):
        if self.status != "SCHEDULED":
            raise ValidationError("Only SCHEDULED appointments can be checked in.")
        from encounters.models import Encounter
        encounter = Encounter.objects.create(
            patient=self.patient,
            appointment=self,
            visit_type="OPD",
            status="REGISTERED",
            created_by=user,
        )
        self.status = "CHECKED_IN"
        self.save(update_fields=["status", "updated_at"])
        return encounter
from django.conf import settings
from django.db import models
from core.models import BaseModel
from encounters.models import Encounter


class UltrasoundReport(BaseModel):
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="ultrasound_reports",
    )
    findings = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="ultrasound/%Y/%m/",
        blank=True,
        null=True,
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ultrasound_reports_performed",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ultrasound_reports_created",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"US #{self.pk} – visit {self.encounter_id}"
"""
injection/models.py
===================
Injection room + minor procedures (including minor surgery).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from encounters.models import Encounter


class InjectionService(BaseModel):
    """
    One procedure episode on a visit (injection, dressing, minor surgery…).
    """

    SERVICE_TYPES = [
        ("INJECTION", "Injection / IM-IV"),
        ("DRESSING", "Wound dressing"),
        ("MINOR_SURGERY", "Minor surgery"),
        ("SUTURE", "Suturing"),
        ("INCISION_DRAINAGE", "Incision & drainage"),
        ("OTHER", "Other procedure"),
    ]

    STATUS_CHOICES = [
        ("DONE", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="injection_services",
    )
    service_type = models.CharField(
        max_length=30,
        choices=SERVICE_TYPES,
        default="INJECTION",
        db_index=True,
    )
    procedure_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g. Excision of lipoma, I&D abscess",
    )
    notes = models.TextField(blank=True)
    materials_used = models.CharField(max_length=255, blank=True)
    complications = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DONE",
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="injection_services_performed",
    )
    performed_at = models.DateTimeField(default=timezone.now)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="injection_services_created",
    )

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "Injection / minor procedure"
        verbose_name_plural = "Injection / minor procedures"

    def __str__(self):
        label = self.get_service_type_display()
        if self.procedure_name:
            return f"{label}: {self.procedure_name}"
        return f"{label} – visit #{self.encounter_id}"
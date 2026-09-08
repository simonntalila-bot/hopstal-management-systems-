"""
patients/models.py
==================
Patient registry, QR ID, optional NHIF flag, past medical documents.
"""

import io
from datetime import date

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q
from django.utils import timezone
import qrcode

from core.models import BaseModel


class PatientManager(models.Manager):
    def active(self):
        return self.filter(is_active=True)

    def search(self, term):
        term = (term or "").strip()
        if not term:
            return self.none()
        return self.filter(
            Q(patient_id__icontains=term)
            | Q(full_name__icontains=term)
            | Q(phone__icontains=term)
            | Q(insurance_number__icontains=term)
            | Q(nhif_card_number__icontains=term)
        )


class Patient(BaseModel):
    GENDER_CHOICES = [("M", "Male"), ("F", "Female"), ("O", "Other")]

    patient_id = models.CharField(
        max_length=20, unique=True, db_index=True, editable=False
    )
    full_name = models.CharField(max_length=200, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    address = models.TextField(blank=True)
    next_of_kin = models.CharField(max_length=200, blank=True)
    next_of_kin_phone = models.CharField(max_length=20, blank=True)

    # General insurance / old field (keep for compatibility)
    insurance_number = models.CharField(
        max_length=50, blank=True, null=True, unique=True, db_index=True
    )

    # NHIF — clinic flag only; claims stay on the separate NHIF portal
    is_nhif = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Patient is an NHIF beneficiary",
    )
    nhif_card_number = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="NHIF card / membership number",
    )

    blood_group = models.CharField(max_length=5, blank=True)
    allergies = models.TextField(blank=True)
    chronic_conditions = models.TextField(blank=True)
    qr_code = models.ImageField(upload_to="patient_qr/", blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)

    objects = PatientManager()

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["full_name", "phone"])]

    def __str__(self):
        return f"{self.patient_id} – {self.full_name}"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day)
            < (self.date_of_birth.month, self.date_of_birth.day)
        )

    def _generate_patient_id(self):
        year = timezone.now().year
        prefix = f"H-{year}-"
        last = (
            Patient.objects.filter(patient_id__startswith=prefix)
            .order_by("-patient_id")
            .first()
        )
        if last:
            try:
                seq = int(last.patient_id.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:05d}"

    def _generate_qr_code(self):
        if not self.patient_id:
            return
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(self.patient_id)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        self.qr_code.save(
            f"{self.patient_id}.png",
            ContentFile(buffer.getvalue()),
            save=False,
        )

    def save(self, *args, **kwargs):
        if not self.patient_id:
            self.patient_id = self._generate_patient_id()
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new or not self.qr_code:
            self._generate_qr_code()
            Patient.objects.filter(pk=self.pk).update(qr_code=self.qr_code)


class PatientDocument(BaseModel):
    """
    Past medical information / scanned records attached to the patient file.
    """
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=150)
    document = models.FileField(upload_to="patient_docs/%Y/%m/")
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_documents_uploaded",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patient_documents_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Patient document"
        verbose_name_plural = "Patient documents"

    def __str__(self):
        return f"{self.title} – {self.patient.patient_id}"
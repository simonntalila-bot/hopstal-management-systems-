"""
consultations/admin.py
"""

from django.contrib import admin
from .models import Consultation, Prescription


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "encounter",
        "doctor",
        "diagnosis",
        "follow_up_date",
        "created_at",
    )
    list_filter = ("created_at", "follow_up_date")
    search_fields = (
        "diagnosis",
        "encounter__patient__patient_id",
        "encounter__patient__first_name",
        "encounter__patient__last_name",
    )
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("encounter", "doctor", "created_by")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "encounter",
        "drug",
        "quantity",
        "source",
        "is_dispensed",
        "doctor",
        "created_at",
    )
    list_filter = ("source", "is_dispensed", "created_at")
    search_fields = (
        "drug__name",
        "encounter__patient__patient_id",
        "encounter__patient__first_name",
        "encounter__patient__last_name",
        "dosage_instructions",
    )
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("encounter", "consultation", "drug", "doctor", "created_by")
    list_editable = ("is_dispensed",)
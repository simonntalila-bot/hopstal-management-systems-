"""
encounters/admin.py
===================
Admin registration for visits, logs, vitals and payments.

Note: date_hierarchy removed — MySQL needs timezone tables for
Django USE_TZ + date_hierarchy (CONVERT_TZ). List still works.
"""

from django.contrib import admin
from .models import Encounter, VisitLog, Vitals, Payment


class VisitLogInline(admin.TabularInline):
    model = VisitLog
    extra = 0
    readonly_fields = (
        "from_status",
        "to_status",
        "from_department",
        "to_department",
        "performed_by",
        "note",
        "timestamp",
    )
    can_delete = False


class VitalsInline(admin.TabularInline):
    model = Vitals
    extra = 0
    readonly_fields = ("recorded_at",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("received_at", "created_at")
    fields = (
        "amount",
        "method",
        "reference",
        "received_by",
        "received_at",
        "notes",
    )


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "status",
        "current_department",
        "created_at",
        "closed_at",
    )
    # Avoid date filters that force CONVERT_TZ until MySQL TZ tables are loaded
    list_filter = ("status", "current_department")
    search_fields = ("patient__patient_id", "patient__full_name")
    readonly_fields = ("created_at", "updated_at", "closed_at")
    inlines = [PaymentInline, VitalsInline, VisitLogInline]
    ordering = ("-created_at",)
    # date_hierarchy = "created_at"  # disabled: needs MySQL timezone tables


@admin.register(VisitLog)
class VisitLogAdmin(admin.ModelAdmin):
    list_display = (
        "encounter",
        "from_status",
        "to_status",
        "from_department",
        "to_department",
        "performed_by",
        "timestamp",
    )
    list_filter = ("to_status", "to_department")
    readonly_fields = (
        "encounter",
        "from_status",
        "to_status",
        "from_department",
        "to_department",
        "performed_by",
        "note",
        "timestamp",
    )
    ordering = ("-timestamp",)


@admin.register(Vitals)
class VitalsAdmin(admin.ModelAdmin):
    list_display = (
        "encounter",
        "temperature_c",
        "blood_pressure",
        "pulse",
        "recorded_at",
    )
    search_fields = ("encounter__patient__patient_id",)
    ordering = ("-recorded_at",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "encounter",
        "amount",
        "method",
        "reference",
        "received_by",
        "received_at",
    )
    list_filter = ("method",)  # removed received_at date filter for same TZ reason
    search_fields = (
        "encounter__patient__patient_id",
        "encounter__patient__full_name",
        "reference",
    )
    readonly_fields = ("received_at", "created_at")
    ordering = ("-received_at",)
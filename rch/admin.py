from django.contrib import admin
from .models import (
    RCHClientProfile,
    RCHVisit,
    ANCRecord,
    Under5Record,
    ImmunizationRecord,
    FamilyPlanningRecord,
    PNCRecord,
)


class ANCInline(admin.StackedInline):
    model = ANCRecord
    extra = 0


class Under5Inline(admin.StackedInline):
    model = Under5Record
    extra = 0


class FPInline(admin.StackedInline):
    model = FamilyPlanningRecord
    extra = 0


class PNCInline(admin.StackedInline):
    model = PNCRecord
    extra = 0


class ImmunizationInline(admin.TabularInline):
    model = ImmunizationRecord
    extra = 0


@admin.register(RCHClientProfile)
class RCHClientProfileAdmin(admin.ModelAdmin):
    list_display = ("patient", "client_type", "gravida", "para", "hiv_status")
    list_filter = ("client_type",)
    search_fields = ("patient__full_name", "patient__patient_id")
    raw_id_fields = ("patient", "mother", "created_by")


@admin.register(RCHVisit)
class RCHVisitAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient",
        "service_type",
        "visit_date",
        "is_high_risk",
        "next_appointment",
        "attended_by",
    )
    list_filter = ("service_type", "is_high_risk", "visit_date")
    search_fields = ("patient__full_name", "patient__patient_id")
    raw_id_fields = ("encounter", "patient", "attended_by", "created_by")
    inlines = [ANCInline, Under5Inline, FPInline, PNCInline, ImmunizationInline]
from django.contrib import admin
from .models import InjectionService


@admin.register(InjectionService)
class InjectionServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "encounter",
        "service_type",
        "procedure_name",
        "status",
        "performed_by",
        "performed_at",
    )
    list_filter = ("service_type", "status", "performed_at")
    search_fields = (
        "procedure_name",
        "notes",
        "encounter__patient__full_name",
        "encounter__patient__patient_id",
    )
    readonly_fields = ("created_at", "updated_at")
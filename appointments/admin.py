from django.contrib import admin
from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("patient", "doctor", "scheduled_at", "status", "department")
    list_filter = ("status", "scheduled_at", "department")
    search_fields = ("patient__patient_id", "patient__full_name", "doctor__username")
    readonly_fields = ("created_at", "updated_at", "created_by")
    date_hierarchy = "scheduled_at"
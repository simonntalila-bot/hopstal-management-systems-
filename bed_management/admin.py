from django.contrib import admin
from .models import Ward, Bed, Admission


class BedInline(admin.TabularInline):
    model = Bed
    extra = 0


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "occupied_count", "available_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    inlines = [BedInline]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ("ward", "bed_number", "status")
    list_filter = ("status", "ward")
    search_fields = ("bed_number", "ward__name")


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ("encounter", "bed", "admitted_at", "discharged_at", "admitted_by")
    list_filter = ("admitted_at", "discharged_at")
    search_fields = ("encounter__patient__patient_id", "bed__bed_number", "bed__ward__name")
    readonly_fields = ("created_at", "updated_at", "admitted_at")
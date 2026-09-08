from django.contrib import admin
from .models import Drug, DispenseRecord


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ("name", "strength", "form", "stock_quantity", "reorder_level", "is_active")
    list_filter = ("is_active", "form")
    search_fields = ("name", "generic_name")
    list_editable = ("stock_quantity", "is_active")


@admin.register(DispenseRecord)
class DispenseRecordAdmin(admin.ModelAdmin):
    list_display = ("drug", "quantity_dispensed", "encounter", "dispensed_by", "dispensed_at")
    list_filter = ("dispensed_at",)
    search_fields = ("drug__name", "encounter__patient__patient_id")
    readonly_fields = ("dispensed_at",)
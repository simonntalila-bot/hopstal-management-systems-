"""
laboratory/admin.py
"""

from django.contrib import admin
from .models import LabTest, LabOrder, LabOrderItem, LabResult


class LabOrderItemInline(admin.TabularInline):
    model = LabOrderItem
    extra = 0


class LabResultInline(admin.StackedInline):
    model = LabResult
    extra = 0
    readonly_fields = ("entered_at", "verified_at")


@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "sample_type", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name")
    list_editable = ("is_active",)


@admin.register(LabOrder)
class LabOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "encounter",
        "status",
        "requested_by",
        "sample_number",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "encounter__patient__patient_id",
        "encounter__patient__full_name",
        "sample_number",
    )
    inlines = [LabOrderItemInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = (
        "order_item",
        "value",
        "is_abnormal",
        "entered_by",
        "entered_at",
    )
    list_filter = ("is_abnormal",)
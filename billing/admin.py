"""
billing/admin.py
================
Admin configuration matching the simplified billing models.
"""

from django.contrib import admin
from .models import Invoice, InvoiceItem, Payment, InsuranceClaim


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = (
        "description",
        "source_type",
        "quantity",
        "unit_price",
        "subtotal",
        "discount_amount",
    )
    readonly_fields = ("created_at",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = (
        "amount",
        "method",
        "reference",
        "received_by",
        "received_at",
        "is_refund",
        "notes",
    )
    readonly_fields = ("received_at", "created_at")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "invoice_number",
        "patient",
        "encounter",
        "total_amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "invoice_number",
        "patient__patient_id",
        "patient__full_name",
    )
    readonly_fields = ("created_at", "updated_at")
    inlines = [InvoiceItemInline, PaymentInline]
    date_hierarchy = "created_at"


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "invoice",
        "description",
        "source_type",
        "quantity",
        "unit_price",
        "subtotal",
    )
    list_filter = ("source_type",)
    search_fields = ("description", "invoice__invoice_number")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "amount",
        "method",
        "reference",
        "invoice",
        "encounter",
        "received_by",
        "received_at",
        "is_refund",
    )
    list_filter = ("method", "is_refund", "received_at")
    search_fields = (
        "reference",
        "invoice__invoice_number",
        "encounter__patient__patient_id",
        "encounter__patient__full_name",
    )
    readonly_fields = ("received_at", "created_at")
    date_hierarchy = "received_at"


@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "claim_number",
        "patient",
        "encounter",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "claim_number",
        "patient__patient_id",
        "patient__full_name",
    )
    readonly_fields = ("created_at", "updated_at")
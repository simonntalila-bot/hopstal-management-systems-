"""
billing/models.py
=================
Formal billing models (Invoice, Payment, InsuranceClaim).

Active day-to-day pay-before-service payments use encounters.Payment.
All related_names here are unique to avoid clashes.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from encounters.models import Encounter
from patients.models import Patient


class Invoice(BaseModel):
    STATUS_CHOICES = [
        ("UNPAID", "Unpaid"),
        ("PARTIALLY_PAID", "Partially Paid"),
        ("PAID", "Paid"),
        ("VOIDED", "Voided"),
    ]

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.PROTECT,
        related_name="billing_invoices",
        null=True,
        blank=True,
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="billing_invoices",
        null=True,
        blank=True,
    )
    invoice_number = models.CharField(max_length=30, unique=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="UNPAID",
        db_index=True,
    )
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_invoices_voided",
    )
    void_reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_invoices_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self):
        return self.invoice_number or f"Invoice #{self.pk}"


class InvoiceItem(BaseModel):
    SOURCE_CHOICES = [
        ("CONSULTATION", "Consultation"),
        ("LAB_TEST", "Lab Test"),
        ("ULTRASOUND", "Ultrasound"),
        ("INJECTION", "Injection"),
        ("MEDICINE", "Medicine"),
        ("RCH_SERVICE", "RCH Service"),
        ("OTHER", "Other"),
    ]

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
    )
    description = models.CharField(max_length=255)
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default="OTHER",
    )
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_invoice_items_created",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Invoice Item"
        verbose_name_plural = "Invoice Items"

    def __str__(self):
        return f"{self.description} ({self.subtotal})"


class Payment(BaseModel):
    METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("BANK", "Bank"),
        ("CARD", "Card"),
        ("OTHER", "Other"),
    ]

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="billing_payments",
        null=True,
        blank=True,
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.PROTECT,
        related_name="billing_payments",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default="CASH",
    )
    reference = models.CharField(max_length=100, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_payments_received",
    )
    received_at = models.DateTimeField(default=timezone.now)
    is_refund = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_payments_created",
    )

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Billing Payment"
        verbose_name_plural = "Billing Payments"

    def __str__(self):
        return f"TZS {self.amount} ({self.method})"


class InsuranceClaim(BaseModel):
    """
    Placeholder for future NHIF claims.
    related_names are deliberately different from Invoice.
    """
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("PAID", "Paid"),
    ]

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="insurance_claims",      # UNIQUE – not billing_invoices
        null=True,
        blank=True,
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.PROTECT,
        related_name="insurance_claims",      # UNIQUE – not billing_invoices
        null=True,
        blank=True,
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_claims",
    )
    claim_number = models.CharField(max_length=50, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="insurance_claims_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Insurance Claim"
        verbose_name_plural = "Insurance Claims"

    def __str__(self):
        return self.claim_number or f"Claim #{self.pk}"
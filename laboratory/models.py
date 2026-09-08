"""
laboratory/models.py
====================
Lab catalog, requests and results for Argentina Dispensary (CDMS).

Cash price on LabTest helps Reception see a suggested amount
when the visit is PAYMENT_PENDING (amount remains editable).

Pay-first: requesting lab sets visit to PAYMENT_PENDING for LAB.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from encounters.models import Encounter


class LabTest(BaseModel):
    """Catalog of lab tests a doctor can request."""

    CATEGORY_CHOICES = [
        ("HEMATOLOGY", "Hematology"),
        ("CHEMISTRY", "Clinical Chemistry"),
        ("LIVER", "Liver Function"),
        ("LIPID", "Lipid Profile"),
        ("INFECTIOUS", "Infectious / Serology"),
        ("HORMONE", "Hormones & Others"),
        ("URINE_STOOL", "Urine & Stool"),
        ("COAGULATION", "Coagulation"),
        ("OTHER", "Other"),
    ]

    code = models.CharField(max_length=30, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="OTHER",
        db_index=True,
    )
    sample_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g. EDTA blood, Serum, Urine, Stool",
    )
    description = models.TextField(blank=True)

    # Cash price shown to Reception on payment pending (TZS)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Cash price in TZS for this test (0 = enter amount manually)",
    )

    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_tests_created",
    )

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Lab Test"
        verbose_name_plural = "Lab Tests"

    def __str__(self):
        if self.price and self.price > 0:
            return f"{self.code} – {self.name} (TZS {self.price:,.0f})"
        return f"{self.code} – {self.name}"


class LabOrder(BaseModel):
    """Lab request header linked to one visit."""

    STATUS_CHOICES = [
        ("REQUESTED", "Requested"),
        ("SAMPLE_COLLECTED", "Sample Collected"),
        ("IN_PROGRESS", "In Progress"),
        ("RESULT_ENTERED", "Result Entered"),
        ("VERIFIED", "Verified"),
        ("RELEASED", "Released to Doctor"),
        ("CANCELLED", "Cancelled"),
    ]

    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.PROTECT,
        related_name="lab_orders",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_orders_requested",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="REQUESTED",
        db_index=True,
    )
    clinical_notes = models.TextField(blank=True)
    sample_number = models.CharField(max_length=30, blank=True, db_index=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_samples_collected",
    )
    released_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_orders_created",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lab Order"
        verbose_name_plural = "Lab Orders"

    def __str__(self):
        return f"LabOrder #{self.pk} – {self.encounter} ({self.status})"

    def suggested_total(self):
        """Sum of cash prices for all items on this order."""
        from decimal import Decimal
        total = Decimal("0")
        for item in self.items.select_related("test").all():
            total += item.test.price or Decimal("0")
        return total


class LabOrderItem(BaseModel):
    """One test line on a lab order."""

    order = models.ForeignKey(
        LabOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    test = models.ForeignKey(
        LabTest,
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_order_items_created",
    )

    class Meta:
        unique_together = ("order", "test")
        verbose_name = "Lab Order Item"
        verbose_name_plural = "Lab Order Items"

    def __str__(self):
        return f"{self.test.code} on Order #{self.order_id}"


class LabResult(BaseModel):
    """Result values for a single ordered test."""

    order_item = models.OneToOneField(
        LabOrderItem,
        on_delete=models.CASCADE,
        related_name="result",
        null=True,
        blank=True,
    )
    value = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)
    is_abnormal = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_results_entered",
    )
    entered_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_results_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lab_results_created",
    )

    class Meta:
        verbose_name = "Lab Result"
        verbose_name_plural = "Lab Results"

    def __str__(self):
        if self.order_item_id and self.order_item.test_id:
            return f"Result for {self.order_item.test.code}"
        return f"LabResult #{self.pk}"
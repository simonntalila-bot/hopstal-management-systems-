"""
pharmacy/models.py
==================
Drug catalog, stock, and dispense records.

unit_price = cash price per base unit (tablet, bottle, vial) in TZS.
stock_quantity always counts base units (pills), not boxes.
pack_size = how many units in one pack (for receive helpers / display).
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel


class Drug(BaseModel):
    name = models.CharField(max_length=150, unique=True, db_index=True)
    generic_name = models.CharField(max_length=150, blank=True)
    strength = models.CharField(max_length=50, blank=True)
    form = models.CharField(
        max_length=50,
        blank=True,
        help_text="Tablet, Syrup, Capsule, Injection",
    )
    unit = models.CharField(
        max_length=30,
        default="tablet",
        help_text="Base unit for stock and price (tablet, bottle, vial)",
    )

    # Stock in base units (e.g. number of tablets)
    stock_quantity = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=10)

    # Optional: tablets (or units) per box/pack when receiving
    pack_size = models.PositiveIntegerField(
        default=1,
        help_text="Units per pack/box (e.g. 100 tablets per box). Use 1 if N/A.",
    )

    # Cash price per base unit (TZS) – used on Payment Pending suggestion
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Cash price per unit (tablet/bottle) in TZS",
    )

    expiry_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Nearest / batch expiry for alert purposes",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drugs_created",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        label = f"{self.name} {self.strength}".strip()
        if self.unit_price and self.unit_price > 0:
            return f"{label} (TZS {self.unit_price:,.0f}/{self.unit})"
        return label

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.reorder_level

    @property
    def is_out_of_stock(self):
        return self.stock_quantity <= 0

    def line_total(self, quantity):
        """Price for quantity base units."""
        qty = quantity or 0
        return (self.unit_price or Decimal("0")) * qty

    def packs_display(self):
        """Human hint: stock as approx packs."""
        if not self.pack_size or self.pack_size <= 1:
            return f"{self.stock_quantity} {self.unit}"
        packs = self.stock_quantity / self.pack_size
        return f"{self.stock_quantity} {self.unit} (~{packs:.1f} packs)"


class StockAdjustment(BaseModel):
    """Manual stock in/out for inventory control."""

    TYPE_CHOICES = [
        ("IN", "Stock In"),
        ("OUT", "Stock Out (adjustment)"),
        ("ADJUST", "Correction"),
    ]
    drug = models.ForeignKey(
        Drug, on_delete=models.CASCADE, related_name="adjustments"
    )
    adjustment_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_adjustments",
    )
    performed_at = models.DateTimeField(default=timezone.now)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_adjustments_created",
    )

    class Meta:
        ordering = ["-performed_at"]

    def __str__(self):
        return f"{self.adjustment_type} {self.quantity} × {self.drug}"


class DispenseRecord(BaseModel):
    encounter = models.ForeignKey(
        "encounters.Encounter",
        on_delete=models.PROTECT,
        related_name="dispense_records",
    )
    prescription = models.ForeignKey(
        "consultations.Prescription",
        on_delete=models.PROTECT,
        related_name="dispense_records",
        null=True,
        blank=True,
    )
    drug = models.ForeignKey(
        Drug, on_delete=models.PROTECT, related_name="dispense_records"
    )
    quantity_dispensed = models.PositiveIntegerField()
    dispensed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispenses_done",
    )
    dispensed_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispense_records_created",
    )

    class Meta:
        ordering = ["-dispensed_at"]

    def __str__(self):
        return f"{self.drug} x{self.quantity_dispensed}"
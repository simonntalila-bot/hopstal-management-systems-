"""
accounts/models.py
==================
Custom User + StaffProfile for Argentina Dispensary (CDMS).

Roles are deliberately lean as confirmed by the client:
- ADMIN (2 accounts)
- RECEPTION (front desk)
- PHARMACY
- DOCTOR
- LAB
- ULTRASOUND
- INJECTION
- RCH
- LABOUR_WARD

Reception and Pharmacy are separate roles; migration 0003 split the original
combined RECEPTION_PHARMACY choice. Every is_*() helper and every
role_required() decorator treats ADMIN as passing all role checks.

No separate Nurse role. Vitals are handled by Reception.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Custom user model.
    Username is the main login field (suitable for shared hospital workstations).
    """
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["username"]

    def __str__(self):
        return self.get_full_name() or self.username

    # ------------------------------------------------------------------
    # RBAC Helper Properties
    # ------------------------------------------------------------------
    @property
    def role(self):
        """Return the staff role code, or None if no profile exists."""
        if hasattr(self, "staff_profile") and self.staff_profile:
            return self.staff_profile.role
        return None

    @property
    def role_display(self):
        """Human-readable role name."""
        if hasattr(self, "staff_profile") and self.staff_profile:
            return self.staff_profile.get_role_display()
        return "No Role"

    def has_role(self, *roles):
        """
        Check if the user has one of the given roles.
        Usage: user.has_role("DOCTOR", "ADMIN")
        """
        return self.role in roles

    def is_admin(self):
        return self.has_role("ADMIN")

    def is_reception(self):
        """Reception (front desk). ADMIN passes every role check by design."""
        return self.has_role("RECEPTION", "ADMIN")

    def is_doctor(self):
        return self.has_role("DOCTOR", "ADMIN")

    def is_lab(self):
        return self.has_role("LAB", "ADMIN")

    def is_ultrasound(self):
        return self.has_role("ULTRASOUND", "ADMIN")

    def is_injection(self):
        return self.has_role("INJECTION", "ADMIN")

    def is_rch(self):
        return self.has_role("RCH", "ADMIN")

    def is_labour(self):
        return self.has_role("LABOUR_WARD", "ADMIN")


class StaffProfile(models.Model):
    """
    Extra information about hospital staff.
    One-to-one with User.
    The 'role' field is the single source of truth for permissions.
    """

    # --------------------------------------------------------------
    # Confirmed lean role set for Argentina Dispensary
    # --------------------------------------------------------------
    ROLE_CHOICES = [
    ("ADMIN", "Admin"),
    ("RECEPTION", "Reception"),
    ("PHARMACY", "Pharmacy"),
    ("DOCTOR", "Doctor"),
    ("LAB", "Laboratory"),
    ("ULTRASOUND", "Ultrasound"),
    ("INJECTION", "Injection Room"),
    ("RCH", "RCH"),
    ("LABOUR_WARD", "Labour Ward"),
]

    EMPLOYMENT_TYPE_CHOICES = [
        ("FULL_TIME", "Full Time"),
        ("PART_TIME", "Part Time"),
        ("CONTRACT", "Contract"),
        ("LOCUM", "Locum"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        db_index=True,
        help_text="Determines what the user can see and do in the system.",
    )
    department = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. OPD, Laboratory, Pharmacy, RCH, Labour Ward",
    )
    phone = models.CharField(max_length=20, blank=True)
    employment_type = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default="FULL_TIME",
    )
    employee_id = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        help_text="Internal staff number (EMP-YYYY-NNNN).",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Profile"
        verbose_name_plural = "Staff Profiles"
        ordering = ["role", "user__last_name"]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.username
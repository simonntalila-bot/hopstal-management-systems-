from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    phone = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["username"]

    def __str__(self):
        return self.get_full_name() or self.username


class StaffProfile(models.Model):
    ROLE_CHOICES = [
        ("ADMIN", "Admin"),
        ("RECEPTIONIST", "Receptionist"),
        ("DOCTOR", "Doctor (Daktari)"),
        ("NURSE", "Nurse (Muuguzi)"),
        ("PHARMACIST", "Pharmacist"),
        ("LAB_TECH", "Lab Technician"),
        ("RADIOLOGIST", "Radiologist / Radiographer"),
        ("ACCOUNTANT", "Accountant (Mhasibu)"),
        ("HR_OFFICER", "HR Officer"),
        ("PROCUREMENT", "Procurement Officer"),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ("FULL_TIME", "Full Time"),
        ("PART_TIME", "Part Time"),
        ("CONTRACT", "Contract"),
        ("LOCUM", "Locum"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, db_index=True)
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default="FULL_TIME")
    employee_id = models.CharField(max_length=30, unique=True, null=True, blank=True)
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
"""
accounts/signals.py
===================
Automatically create a StaffProfile whenever a new User is created.
Uses get_or_create to avoid duplicate errors.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User, StaffProfile


@receiver(post_save, sender=User)
def create_staff_profile(sender, instance, created, **kwargs):
    """
    When a new User is created, automatically create a StaffProfile
    only if one does not already exist.
    """
    if created:
        StaffProfile.objects.get_or_create(user=instance)
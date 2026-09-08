"""
accounts/admin.py
=================
Admin configuration for User and StaffProfile.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, StaffProfile


class StaffProfileInline(admin.StackedInline):
    """
    Show StaffProfile fields inside the User edit page.
    """
    model = StaffProfile
    can_delete = False
    verbose_name_plural = "Staff Profile"
    fk_name = "user"
    extra = 0
    max_num = 1
    fields = (
        "role",
        "department",
        "phone",
        "employment_type",
        "employee_id",
        "is_active",
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "get_role",
    )
    list_filter = ("is_staff", "is_superuser", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    inlines = [StaffProfileInline]

    def get_role(self, obj):
        if hasattr(obj, "staff_profile") and obj.staff_profile:
            return obj.staff_profile.get_role_display()
        return "—"
    get_role.short_description = "Role"


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "department", "employee_id", "is_active")
    list_filter = ("role", "is_active", "employment_type")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "employee_id",
    )
    readonly_fields = ("created_at", "updated_at")
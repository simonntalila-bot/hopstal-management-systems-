from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "model_name", "object_id", "user", "timestamp")
    list_filter = ("action", "model_name", "timestamp")
    search_fields = ("model_name", "object_id", "user__username")
    readonly_fields = ("user", "model_name", "object_id", "action", "changes", "ip_address", "timestamp")
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'event_type', 'user', 'hash')
    list_filter = ('event_type', 'created_at')
    search_fields = ('event_type', 'payload')
    readonly_fields = ('id', 'event_type', 'payload', 'user', 'hash', 'previous_hash', 'chain_hash', 'created_at')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

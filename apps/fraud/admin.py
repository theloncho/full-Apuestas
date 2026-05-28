from django.contrib import admin
from .models import SuspiciousActivity


@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'rule_type', 'user', 'ip_address', 'reviewed', 'reviewed_by')
    list_filter = ('rule_type', 'reviewed', 'created_at')
    search_fields = ('user__username', 'ip_address', 'description')
    readonly_fields = ('rule_type', 'user', 'ip_address', 'description', 'metadata', 'created_at')
    actions = ['mark_reviewed']

    @admin.action(description='Marcar como revisado')
    def mark_reviewed(self, request, queryset):
        from django.utils import timezone
        queryset.update(reviewed=True, reviewed_by=request.user, reviewed_at=timezone.now())

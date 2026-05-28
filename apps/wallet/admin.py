from django.contrib import admin
from .models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'account_type', 'user', 'direction', 'amount', 'transaction_id', 'description')
    list_filter = ('account_type', 'direction', 'created_at')
    search_fields = ('transaction_id', 'description')
    readonly_fields = (
        'id', 'account_type', 'user', 'amount', 'direction',
        'transaction_id', 'description', 'created_at', 'bet',
    )
    ordering = ('-created_at',)

    def has_change_permission(self, request, obj=None):
        return False  # Append-only

    def has_delete_permission(self, request, obj=None):
        return False  # Append-only

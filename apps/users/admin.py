from django.contrib import admin
from .models import User, GamblingLimit


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'dni', 'account_status', 'birth_date', 'is_active_for_betting')
    list_filter = ('account_status',)
    search_fields = ('username', 'dni', 'email')
    readonly_fields = ('last_login_ip',)


@admin.register(GamblingLimit)
class GamblingLimitAdmin(admin.ModelAdmin):
    list_display = ('user', 'limit_type', 'amount', 'pending_amount', 'pending_effective_at')
    list_filter = ('limit_type',)

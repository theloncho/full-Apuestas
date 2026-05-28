from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import SuspiciousActivity, AlertStatus, AlertSeverity


@admin.register(SuspiciousActivity)
class SuspiciousActivityAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'activity_type',
        'severity_badge',
        'user',
        'ip_address',
        'status_badge',
        'reviewed_by',
    )
    list_filter = ('activity_type', 'severity', 'status', 'created_at')
    search_fields = ('user__username', 'ip_address', 'reason')
    readonly_fields = (
        'activity_type', 'severity', 'user', 'ip_address',
        'reason', 'metadata', 'created_at', 'reviewed_at', 'reviewed_by',
    )
    ordering = ('-created_at',)
    actions = ['mark_reviewed', 'mark_confirmed', 'mark_dismissed']

    # ─── Badges de color ──────────────────────────────────────────────────

    @admin.display(description='Severidad')
    def severity_badge(self, obj):
        colors = {
            AlertSeverity.LOW: '#28a745',
            AlertSeverity.MEDIUM: '#fd7e14',
            AlertSeverity.HIGH: '#dc3545',
            AlertSeverity.CRITICAL: '#6f42c1',
        }
        color = colors.get(obj.severity, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color,
            obj.get_severity_display(),
        )

    @admin.display(description='Estado')
    def status_badge(self, obj):
        colors = {
            AlertStatus.PENDING: '#ffc107',
            AlertStatus.REVIEWED: '#17a2b8',
            AlertStatus.DISMISSED: '#6c757d',
            AlertStatus.CONFIRMED: '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color,
            obj.get_status_display(),
        )

    # ─── Acciones ─────────────────────────────────────────────────────────

    @admin.action(description='✅ Marcar como revisada')
    def mark_reviewed(self, request, queryset):
        updated = queryset.filter(status=AlertStatus.PENDING).update(
            status=AlertStatus.REVIEWED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f'{updated} alerta(s) marcada(s) como revisada(s).')

    @admin.action(description='🚨 Marcar como fraude confirmado')
    def mark_confirmed(self, request, queryset):
        updated = queryset.exclude(status=AlertStatus.CONFIRMED).update(
            status=AlertStatus.CONFIRMED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f'{updated} alerta(s) confirmada(s) como fraude.')

    @admin.action(description='🗑️ Descartar alerta')
    def mark_dismissed(self, request, queryset):
        updated = queryset.exclude(status=AlertStatus.DISMISSED).update(
            status=AlertStatus.DISMISSED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        self.message_user(request, f'{updated} alerta(s) descartada(s).')

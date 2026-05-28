from django.db import models


class FraudRuleType(models.TextChoices):
    SAME_IP_MULTIPLE_ACCOUNTS = 'same_ip_multi_account', 'Misma IP, múltiples cuentas'
    IDENTICAL_BET_PATTERN = 'identical_bet_pattern', 'Patrón de apuestas idénticas'
    DEPOSIT_THEN_CASHOUT = 'deposit_cashout', 'Depósito inmediato + cash-out'
    BONUS_ABUSE = 'bonus_abuse', 'Abuso de bono'
    OPPOSITE_BETS_HEDGING = 'opposite_bets_hedging', 'Apuestas opuestas o cobertura'

class AlertSeverity(models.TextChoices):
    LOW = 'low', 'Baja'
    MEDIUM = 'medium', 'Media'
    HIGH = 'high', 'Alta'
    CRITICAL = 'critical', 'Crítica'

class AlertStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    REVIEWED = 'reviewed', 'Revisada'
    DISMISSED = 'dismissed', 'Descartada'
    CONFIRMED = 'confirmed', 'Confirmada'

class SuspiciousActivity(models.Model):
    """Alerta de actividad sospechosa para revisión manual del admin."""
    activity_type = models.CharField(max_length=50, choices=FraudRuleType.choices)
    severity = models.CharField(max_length=20, choices=AlertSeverity.choices, default=AlertSeverity.LOW)
    user = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='suspicious_activities',
        null=True, blank=True,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    reason = models.TextField()
    metadata = models.JSONField(default=dict)
    
    status = models.CharField(max_length=20, choices=AlertStatus.choices, default=AlertStatus.PENDING)
    
    reviewed_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_activities',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Actividad sospechosa'
        verbose_name_plural = 'Actividades sospechosas'

    def __str__(self):
        return f"[{self.get_severity_display()}] [{self.get_activity_type_display()}] {self.user} - {self.status}"

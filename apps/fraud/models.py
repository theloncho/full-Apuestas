from django.db import models


class FraudRuleType(models.TextChoices):
    SAME_IP_MULTIPLE_ACCOUNTS = 'same_ip_multi_account', 'Misma IP, múltiples cuentas'
    IDENTICAL_BET_PATTERN = 'identical_bet_pattern', 'Patrón de apuestas idénticas'
    DEPOSIT_THEN_CASHOUT = 'deposit_cashout', 'Depósito inmediato + cash-out'
    BONUS_ABUSE = 'bonus_abuse', 'Abuso de bono'


class SuspiciousActivity(models.Model):
    """Alerta de actividad sospechosa para revisión manual del admin."""
    rule_type = models.CharField(max_length=50, choices=FraudRuleType.choices)
    user = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='suspicious_activities',
        null=True, blank=True,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField()
    metadata = models.JSONField(default=dict)
    reviewed = models.BooleanField(default=False)
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
        return f"[{self.get_rule_type_display()}] {self.user} - {self.created_at}"

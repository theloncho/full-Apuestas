from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import re


def validate_dni_peruano(dni: str) -> bool:
    """
    Valida el formato del DNI peruano: exactamente 8 dígitos numéricos.
    La verificación real de existencia se delega a la API de RENIEC (APISPerú).
    Nota: RENIEC no publica el algoritmo oficial de dígito verificador, por lo
    que cualquier implementación de mod-11 es incorrecta para DNIs reales.
    """
    return bool(re.match(r'^\d{8}$', dni))


class AccountStatus(models.TextChoices):
    PENDING = 'pendiente_verificacion', 'Pendiente de verificación'
    VERIFIED = 'verificado', 'Verificado'
    BLOCKED = 'bloqueado', 'Bloqueado'
    SELF_EXCLUDED = 'autoexcluido', 'Autoexcluido'


class User(AbstractUser):
    """
    Usuario con KYC simulado.
    Extiende AbstractUser con DNI peruano, fecha de nacimiento,
    estados de cuenta y controles de juego responsable.
    """
    dni = models.CharField(max_length=8, unique=True)
    birth_date = models.DateField()
    phone = models.CharField(max_length=20, blank=True)
    account_status = models.CharField(
        max_length=30,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
    )
    # Autoexclusión
    self_excluded_until = models.DateTimeField(null=True, blank=True)
    self_excluded_permanent = models.BooleanField(default=False)
    # 2FA
    totp_secret = models.CharField(max_length=32, blank=True)
    totp_enabled = models.BooleanField(default=False)
    # Anti-fraude
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'users_user'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    @property
    def is_of_age(self) -> bool:
        """Verifica mayoría de edad (≥ 18 años)."""
        today = date.today()
        age = today.year - self.birth_date.year - (
            (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
        )
        return age >= 18

    @property
    def is_active_for_betting(self) -> bool:
        """¿Puede apostar? Solo si verificado y no autoexcluido."""
        if self.account_status != AccountStatus.VERIFIED:
            return False
        if self.self_excluded_permanent:
            return False
        if self.self_excluded_until and timezone.now() < self.self_excluded_until:
            return False
        return True

    def apply_self_exclusion(self, days: int | None):
        """
        Autoexclusión: temporal (7/30/90 días) o indefinida.
        days=None → exclusión permanente.
        El usuario NO puede revertirla antes del tiempo.
        """
        if days is None:
            self.self_excluded_permanent = True
            self.account_status = AccountStatus.SELF_EXCLUDED
        else:
            self.self_excluded_until = timezone.now() + timedelta(days=days)
            self.account_status = AccountStatus.SELF_EXCLUDED
        self.save()

    def __str__(self):
        return f"{self.username} ({self.get_account_status_display()})"


class GamblingLimitType(models.TextChoices):
    DAILY = 'diario', 'Diario'
    WEEKLY = 'semanal', 'Semanal'
    MONTHLY = 'mensual', 'Mensual'


class GamblingLimit(models.Model):
    """
    Límite de depósito de fichas configurable por el usuario.
    Regla crítica (Ley 31557):
      - Bajar límite: efectivo INMEDIATAMENTE.
      - Subir límite: cooldown de 24 horas.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='limits'
    )
    limit_type = models.CharField(
        max_length=10, choices=GamblingLimitType.choices
    )
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    # Pending change (para el cooldown al subir)
    pending_amount = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    pending_effective_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'limit_type')
        verbose_name = 'Límite de juego'
        verbose_name_plural = 'Límites de juego'

    def update_limit(self, new_amount: Decimal):
        """
        Actualiza el límite de depósito.
        - Si baja: efectivo inmediatamente.
        - Si sube: cooldown de 24 horas.
        """
        if new_amount <= self.amount:
            # Bajar: inmediato
            self.amount = new_amount
            self.pending_amount = None
            self.pending_effective_at = None
        else:
            # Subir: cooldown 24h
            self.pending_amount = new_amount
            self.pending_effective_at = timezone.now() + timedelta(hours=24)
        self.save()

    def apply_pending_if_ready(self):
        """Aplica el cambio pendiente si ya pasaron las 24h."""
        if self.pending_amount and self.pending_effective_at:
            if timezone.now() >= self.pending_effective_at:
                self.amount = self.pending_amount
                self.pending_amount = None
                self.pending_effective_at = None
                self.save()

    def __str__(self):
        return f"{self.user.username} - {self.get_limit_type_display()}: {self.amount}"

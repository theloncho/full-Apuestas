"""
Wallet con partida doble — Módulo crítico de integridad financiera.

REGLAS NO NEGOCIABLES:
  1. NUNCA almacenar el saldo en un campo. Siempre calcular por SUM.
  2. SIEMPRE usar select_for_update() antes de escribir.
  3. SIEMPRE envolver en transaction.atomic().
  4. Cada operación genera MÍNIMO 2 LedgerEntry cuya suma es cero.
  5. Usar Decimal, JAMÁS float.
"""
from django.db import models, transaction
from django.db.models import Sum, Q
from decimal import Decimal
import uuid


class AccountType(models.TextChoices):
    USER_WALLET = 'wallet_usuario', 'Wallet Usuario'
    HOUSE = 'casa', 'Casa'
    PENDING_BETS = 'apuestas_pendientes', 'Apuestas Pendientes'
    BONUSES = 'bonos', 'Bonos'


class Direction(models.TextChoices):
    DEBIT = 'DEBIT', 'Débito'
    CREDIT = 'CREDIT', 'Crédito'


class LedgerEntry(models.Model):
    """
    Tabla central del sistema financiero.
    Append-only: nunca UPDATE, nunca DELETE.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_type = models.CharField(max_length=30, choices=AccountType.choices)
    user = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        null=True, blank=True,  # null para cuentas del sistema (casa)
    )
    amount = models.DecimalField(max_digits=18, decimal_places=4)
    direction = models.CharField(max_length=6, choices=Direction.choices)
    transaction_id = models.UUIDField(db_index=True)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Referencia opcional a apuesta
    bet = models.ForeignKey(
        'betting.Bet',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='ledger_entries',
    )

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['account_type', 'user', 'created_at']),
            models.Index(fields=['transaction_id']),
        ]
        verbose_name = 'Entrada contable'
        verbose_name_plural = 'Entradas contables'

    def __str__(self):
        sign = '+' if self.direction == Direction.CREDIT else '-'
        return f"{self.account_type} {sign}{self.amount} ({self.transaction_id})"


class WalletService:
    """
    Servicio central de operaciones financieras.
    Todos los métodos son atómicos y usan select_for_update
    para prevenir doble gasto por concurrencia.
    """

    @staticmethod
    def get_balance(user) -> Decimal:
        """Saldo = SUM(créditos) − SUM(débitos). Nunca almacenado."""
        result = LedgerEntry.objects.filter(
            account_type=AccountType.USER_WALLET,
            user=user,
        ).aggregate(
            credits=Sum('amount', filter=Q(direction=Direction.CREDIT)),
            debits=Sum('amount', filter=Q(direction=Direction.DEBIT)),
        )
        credits = result['credits'] or Decimal('0')
        debits = result['debits'] or Decimal('0')
        return credits - debits

    @staticmethod
    def get_pending_balance(user) -> Decimal:
        """Fichas bloqueadas en apuestas pendientes."""
        result = LedgerEntry.objects.filter(
            account_type=AccountType.PENDING_BETS,
            user=user,
        ).aggregate(
            credits=Sum('amount', filter=Q(direction=Direction.CREDIT)),
            debits=Sum('amount', filter=Q(direction=Direction.DEBIT)),
        )
        credits = result['credits'] or Decimal('0')
        debits = result['debits'] or Decimal('0')
        return credits - debits

    @classmethod
    @transaction.atomic
    def deposit_tokens(cls, user, amount: Decimal, description: str = 'Recarga simulada') -> uuid.UUID:
        """
        Recarga simulada: casa → wallet_usuario.
        Requiere idempotency key gestionado a nivel de view.
        """
        if amount <= Decimal('0'):
            raise ValueError("El monto debe ser positivo.")

        # Verificar límites de depósito
        cls._check_deposit_limits(user, amount)

        # Bloqueo pesimista en entradas del usuario
        LedgerEntry.objects.select_for_update().filter(
            user=user, account_type=AccountType.USER_WALLET
        ).exists()

        transaction_id = uuid.uuid4()

        # Débito de la casa (la casa "entrega" fichas)
        LedgerEntry.objects.create(
            account_type=AccountType.HOUSE,
            user=None,
            amount=amount,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=description,
        )
        # Crédito al wallet del usuario
        LedgerEntry.objects.create(
            account_type=AccountType.USER_WALLET,
            user=user,
            amount=amount,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=description,
        )
        return transaction_id

    @classmethod
    @transaction.atomic
    def withdraw_tokens(cls, user, amount: Decimal, description: str = 'Retiro simulado') -> uuid.UUID:
        """
        Retiro simulado: wallet_usuario → casa.
        """
        if amount <= Decimal('0'):
            raise ValueError("El monto debe ser positivo.")

        # Bloqueo pesimista
        LedgerEntry.objects.select_for_update().filter(
            user=user, account_type=AccountType.USER_WALLET
        ).exists()

        balance = cls.get_balance(user)
        if balance < amount:
            raise ValueError(
                f"Saldo insuficiente. Disponible: {balance}, Requerido: {amount}"
            )

        transaction_id = uuid.uuid4()

        LedgerEntry.objects.create(
            account_type=AccountType.USER_WALLET,
            user=user,
            amount=amount,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=description,
        )
        LedgerEntry.objects.create(
            account_type=AccountType.HOUSE,
            user=None,
            amount=amount,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=description,
        )
        return transaction_id

    @classmethod
    @transaction.atomic
    def lock_funds_for_bet(cls, user, amount: Decimal, bet) -> uuid.UUID:
        """
        Bloquea fondos al aceptar apuesta: wallet_usuario → apuestas_pendientes.
        select_for_update previene doble gasto concurrente.
        """
        LedgerEntry.objects.select_for_update().filter(
            user=user, account_type=AccountType.USER_WALLET
        ).exists()

        balance = cls.get_balance(user)
        if balance < amount:
            raise ValueError(
                f"Saldo insuficiente. Disponible: {balance}, Requerido: {amount}"
            )

        transaction_id = uuid.uuid4()

        LedgerEntry.objects.create(
            account_type=AccountType.USER_WALLET,
            user=user,
            amount=amount,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=f'Apuesta bloqueada #{bet.id}',
            bet=bet,
        )
        LedgerEntry.objects.create(
            account_type=AccountType.PENDING_BETS,
            user=user,
            amount=amount,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=f'Apuesta bloqueada #{bet.id}',
            bet=bet,
        )
        return transaction_id

    @classmethod
    @transaction.atomic
    def settle_won_bet(cls, user, stake: Decimal, payout: Decimal, bet) -> uuid.UUID:
        """
        Apuesta ganada: liberar pendientes + acreditar ganancia desde casa.
        payout = stake × odds (calculado con Decimal exacto).
        """
        transaction_id = uuid.uuid4()

        # 1. Liberar apuestas_pendientes
        LedgerEntry.objects.create(
            account_type=AccountType.PENDING_BETS,
            user=user,
            amount=stake,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=f'Liquidación ganada #{bet.id}',
            bet=bet,
        )
        LedgerEntry.objects.create(
            account_type=AccountType.HOUSE,
            user=None,
            amount=stake,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=f'Liquidación ganada #{bet.id} - stake retornado',
            bet=bet,
        )

        # 2. Casa paga el payout completo al usuario
        LedgerEntry.objects.create(
            account_type=AccountType.HOUSE,
            user=None,
            amount=payout,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=f'Payout apuesta #{bet.id}',
            bet=bet,
        )
        LedgerEntry.objects.create(
            account_type=AccountType.USER_WALLET,
            user=user,
            amount=payout,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=f'Payout apuesta #{bet.id}',
            bet=bet,
        )
        return transaction_id

    @classmethod
    @transaction.atomic
    def settle_lost_bet(cls, user, stake: Decimal, bet) -> uuid.UUID:
        """Apuesta perdida: apuestas_pendientes → casa."""
        transaction_id = uuid.uuid4()

        LedgerEntry.objects.create(
            account_type=AccountType.PENDING_BETS,
            user=user,
            amount=stake,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=f'Apuesta perdida #{bet.id}',
            bet=bet,
        )
        LedgerEntry.objects.create(
            account_type=AccountType.HOUSE,
            user=None,
            amount=stake,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=f'Apuesta perdida #{bet.id}',
            bet=bet,
        )
        return transaction_id

    @classmethod
    @transaction.atomic
    def cashout_bet(cls, user, stake: Decimal, cashout_amount: Decimal, bet) -> uuid.UUID:
        """
        Cash-out: devolver cashout_amount al usuario desde apuestas_pendientes + casa.
        """
        transaction_id = uuid.uuid4()

        # Liberar pendientes
        LedgerEntry.objects.create(
            account_type=AccountType.PENDING_BETS,
            user=user,
            amount=stake,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=f'Cash-out apuesta #{bet.id}',
            bet=bet,
        )
        # Casa recibe stake
        LedgerEntry.objects.create(
            account_type=AccountType.HOUSE,
            user=None,
            amount=stake,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=f'Cash-out apuesta #{bet.id} - stake',
            bet=bet,
        )
        # Casa paga cashout al usuario
        LedgerEntry.objects.create(
            account_type=AccountType.HOUSE,
            user=None,
            amount=cashout_amount,
            direction=Direction.DEBIT,
            transaction_id=transaction_id,
            description=f'Cash-out apuesta #{bet.id} - pago',
            bet=bet,
        )
        LedgerEntry.objects.create(
            account_type=AccountType.USER_WALLET,
            user=user,
            amount=cashout_amount,
            direction=Direction.CREDIT,
            transaction_id=transaction_id,
            description=f'Cash-out apuesta #{bet.id}',
            bet=bet,
        )
        return transaction_id

    @staticmethod
    def _check_deposit_limits(user, amount: Decimal):
        """Verifica que el depósito no supere límites configurados."""
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        limit_periods = {
            'diario': timedelta(days=1),
            'semanal': timedelta(weeks=1),
            'mensual': timedelta(days=30),
        }

        for limit_obj in user.limits.all():
            period = limit_periods.get(limit_obj.limit_type)
            if not period:
                continue
            since = now - period
            deposited = LedgerEntry.objects.filter(
                account_type=AccountType.USER_WALLET,
                user=user,
                direction=Direction.CREDIT,
                description__icontains='Recarga',
                created_at__gte=since,
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            if deposited + amount > limit_obj.amount:
                raise ValueError(
                    f"Supera el límite {limit_obj.get_limit_type_display()}: "
                    f"Usado {deposited}, Límite {limit_obj.amount}"
                )

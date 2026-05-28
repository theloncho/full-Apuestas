from django.db import models
from django.utils import timezone
from django_fsm import FSMField, transition
from decimal import Decimal, ROUND_HALF_UP
import uuid


class EventStatus(models.TextChoices):
    SCHEDULED = 'programado', 'Programado'
    LIVE = 'en_vivo', 'En vivo'
    FINISHED = 'finalizado', 'Finalizado'
    SUSPENDED = 'suspendido', 'Suspendido'
    CANCELLED = 'anulado', 'Anulado'


class MarketType(models.TextChoices):
    HOME_DRAW_AWAY = '1X2', 'Resultado (1X2)'
    OVER_UNDER = 'over_under', 'Más/Menos goles'
    BTTS = 'btts', 'Ambos equipos anotan'
    ASIAN_HANDICAP = 'handicap_asiatico', 'Handicap asiático'


class BetStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    ACCEPTED = 'accepted', 'Aceptada'
    SETTLING = 'settling', 'Liquidando'
    WON = 'won', 'Ganada'
    LOST = 'lost', 'Perdida'
    VOID = 'void', 'Anulada'
    CASHED_OUT = 'cashed_out', 'Cash-out'
    SETTLED = 'settled', 'Liquidada'


class Sport(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, default='bi-trophy')

    class Meta:
        verbose_name = 'Deporte'
        verbose_name_plural = 'Deportes'

    def __str__(self):
        return self.name


class Event(models.Model):
    """
    Evento deportivo con máquina de estados:
    programado → en_vivo → finalizado
                        → suspendido
                        → anulado
    """
    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, related_name='events')
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    scheduled_at = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.SCHEDULED,
        db_index=True,
    )
    result_home = models.IntegerField(null=True, blank=True)
    result_away = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_at']
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} ({self.scheduled_at.strftime('%d/%m/%Y %H:%M')})"


class Market(models.Model):
    """Mercado de apuestas dentro de un evento."""
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='markets')
    market_type = models.CharField(max_length=30, choices=MarketType.choices)
    is_suspended = models.BooleanField(default=False)
    suspended_until = models.DateTimeField(null=True, blank=True)
    # Para over/under: línea (ej. 2.5)
    line = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('event', 'market_type', 'line')
        verbose_name = 'Mercado'
        verbose_name_plural = 'Mercados'

    def __str__(self):
        label = self.get_market_type_display()
        if self.line:
            label += f' ({self.line})'
        return f"{self.event} - {label}"


class Selection(models.Model):
    """Una selección posible dentro de un mercado (ej: '1', 'X', '2', 'Over 2.5')."""
    market = models.ForeignKey(Market, on_delete=models.CASCADE, related_name='selections')
    name = models.CharField(max_length=100)
    odds = models.DecimalField(max_digits=10, decimal_places=4)
    is_winner = models.BooleanField(null=True, blank=True)  # null = no resuelto
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Selección'
        verbose_name_plural = 'Selecciones'

    def __str__(self):
        return f"{self.name} @ {self.odds}"


class Bet(models.Model):
    """
    Apuesta simple con FSM (django-fsm).

    Ciclo de vida:
    pending → accepted → settling → won/lost/void/cashed_out → settled

    Cada transición dispara operaciones de wallet atómicas.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name='bets')
    selection = models.ForeignKey(Selection, on_delete=models.PROTECT, related_name='bets')
    stake = models.DecimalField(max_digits=18, decimal_places=4)
    odds_at_placement = models.DecimalField(max_digits=10, decimal_places=4)
    status = FSMField(default=BetStatus.PENDING, choices=BetStatus.choices, db_index=True)
    payout = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    cashout_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    # Idempotencia
    idempotency_key = models.UUIDField(unique=True, null=True, blank=True)

    class Meta:
        ordering = ['-placed_at']
        verbose_name = 'Apuesta'
        verbose_name_plural = 'Apuestas'

    # ─── Transiciones FSM ────────────────────────────────────────────────────

    @transition(field=status, source=BetStatus.PENDING, target=BetStatus.ACCEPTED)
    def accept(self):
        """Bloquear fondos vía WalletService."""
        from apps.wallet.models import WalletService
        WalletService.lock_funds_for_bet(self.user, self.stake, self)
        from apps.audit.models import AuditLog
        AuditLog.log(
            'bet_accepted',
            {'bet_id': str(self.id), 'stake': str(self.stake), 'odds': str(self.odds_at_placement)},
            self.user,
        )

    @transition(field=status, source=BetStatus.ACCEPTED, target=BetStatus.SETTLING)
    def start_settling(self):
        """Marca la apuesta como en proceso de liquidación."""
        pass

    @transition(field=status, source=BetStatus.SETTLING, target=BetStatus.WON)
    def mark_won(self):
        """Apuesta ganada: calcular y acreditar payout."""
        from apps.wallet.models import WalletService
        payout = (self.stake * self.odds_at_placement).quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP
        )
        self.payout = payout
        self.settled_at = timezone.now()
        WalletService.settle_won_bet(self.user, self.stake, payout, self)
        from apps.audit.models import AuditLog
        AuditLog.log(
            'bet_won',
            {'bet_id': str(self.id), 'payout': str(payout)},
            self.user,
        )

    @transition(field=status, source=BetStatus.SETTLING, target=BetStatus.LOST)
    def mark_lost(self):
        """Apuesta perdida: transferir stake a la casa."""
        from apps.wallet.models import WalletService
        self.payout = Decimal('0')
        self.settled_at = timezone.now()
        WalletService.settle_lost_bet(self.user, self.stake, self)
        from apps.audit.models import AuditLog
        AuditLog.log('bet_lost', {'bet_id': str(self.id)}, self.user)

    @transition(
        field=status,
        source=[BetStatus.WON, BetStatus.LOST, BetStatus.VOID, BetStatus.CASHED_OUT],
        target=BetStatus.SETTLED,
    )
    def settle(self):
        """Marca la apuesta como completamente liquidada."""
        pass

    @transition(field=status, source=BetStatus.ACCEPTED, target=BetStatus.VOID)
    def void_bet(self):
        """Anular apuesta (evento anulado): devolver stake."""
        from apps.wallet.models import WalletService
        self.settled_at = timezone.now()
        WalletService.cashout_bet(self.user, self.stake, self.stake, self)
        from apps.audit.models import AuditLog
        AuditLog.log('bet_voided', {'bet_id': str(self.id)}, self.user)

    @transition(field=status, source=BetStatus.ACCEPTED, target=BetStatus.CASHED_OUT)
    def cash_out(self, cashout_amount: Decimal = None):
        """Cash-out anticipado a cuota calculada."""
        from apps.wallet.models import WalletService
        if cashout_amount is None:
            cashout_amount = self.calculated_cashout
        cashout_amount = cashout_amount.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        self.cashout_amount = cashout_amount
        self.settled_at = timezone.now()
        WalletService.cashout_bet(self.user, self.stake, cashout_amount, self)
        from apps.audit.models import AuditLog
        AuditLog.log(
            'bet_cashed_out',
            {'bet_id': str(self.id), 'cashout': str(cashout_amount)},
            self.user,
        )

    @property
    def potential_payout(self) -> Decimal:
        """Pago potencial si la apuesta se gana."""
        return (self.stake * self.odds_at_placement).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    @property
    def calculated_cashout(self) -> Decimal:
        """
        Fórmula: cashout = stake × odds_original / odds_actual × factor_casa
        factor_casa = 0.95
        """
        current_odds = self.selection.odds
        if current_odds <= Decimal('0'):
            return Decimal('0')
        HOUSE_FACTOR = Decimal('0.95')
        cashout = (
            self.stake * self.odds_at_placement / current_odds * HOUSE_FACTOR
        )
        return cashout.quantize(Decimal('0.0001'))

    def __str__(self):
        return f"Bet {self.id} - {self.user.username} - {self.get_status_display()}"


class CombinedBet(models.Model):
    """
    Apuesta combinada (acumuladora).
    Cuota final = ∏ odds de cada selección.
    Si una falla, la combinada pierde.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name='combined_bets')
    selections = models.ManyToManyField(Selection, related_name='combined_bets')
    stake = models.DecimalField(max_digits=18, decimal_places=4)
    combined_odds = models.DecimalField(max_digits=18, decimal_places=4)
    status = FSMField(default=BetStatus.PENDING, db_index=True)
    payout = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.UUIDField(unique=True, null=True, blank=True)

    class Meta:
        ordering = ['-placed_at']
        verbose_name = 'Apuesta combinada'
        verbose_name_plural = 'Apuestas combinadas'

    def calculate_combined_odds(self) -> Decimal:
        """Calcula cuota combinada = producto de cuotas individuales."""
        odds = Decimal('1')
        for sel in self.selections.all():
            odds *= sel.odds
        return odds.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    def __str__(self):
        count = self.selections.count()
        return f"Combinada {self.id} ({count} selecciones) - {self.get_status_display()}"

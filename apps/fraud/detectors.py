from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import SuspiciousActivity, FraudRuleType, AlertSeverity, AlertStatus
from apps.wallet.models import LedgerEntry, AccountType, Direction
from apps.audit.models import AuditLog


SAME_IP_THRESHOLD = 5
SAME_IP_WINDOW_HOURS = 24

CASHOUT_WINDOW_MINUTES = 10

IDENTICAL_BET_THRESHOLD = 4
IDENTICAL_BET_WINDOW_MINUTES = 5


def _create_alert(user, activity_type, severity, reason, metadata=None, ip_address=None):
    """Helper to create alerts, log them, and apply blocking logic."""
    if metadata is None:
        metadata = {}

    # Check for recent unreviewed duplicates
    window = timezone.now() - timedelta(hours=24)
    if SuspiciousActivity.objects.filter(
        user=user,
        activity_type=activity_type,
        status=AlertStatus.PENDING,
        created_at__gte=window
    ).exists():
        return  # Prevent spamming the same alert for the user

    alert = SuspiciousActivity.objects.create(
        user=user,
        activity_type=activity_type,
        severity=severity,
        reason=reason,
        ip_address=ip_address,
        metadata=metadata
    )

    # Log to immutable audit chain
    AuditLog.log('fraud_alert_created', {
        'alert_id': str(alert.id),
        'activity_type': activity_type,
        'severity': severity,
        'user_id': user.id if user else None,
        'reason': reason,
    }, user=user)

    # Block automatically if severity is HIGH or CRITICAL
    if severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL] and user:
        from apps.users.models import AccountStatus
        user.account_status = AccountStatus.SUSPENDED
        user.is_active = False
        user.save(update_fields=['account_status', 'is_active'])
        
        AuditLog.log('user_auto_suspended', {
            'reason': 'Auto-suspended due to high severity fraud alert',
            'alert_id': str(alert.id)
        }, user=user)


def check_same_ip(user, ip_address: str):
    """Detecta si la misma IP se usa por múltiples cuentas en 24 horas."""
    if not ip_address:
        return
        
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Check users with last login from this IP
    count = User.objects.filter(last_login_ip=ip_address).count()

    if count >= SAME_IP_THRESHOLD:
        _create_alert(
            user=user,
            activity_type=FraudRuleType.SAME_IP_MULTIPLE_ACCOUNTS,
            severity=AlertSeverity.HIGH,
            reason=f"IP {ip_address} usada por {count} cuentas distintas.",
            ip_address=ip_address,
            metadata={'ip': ip_address, 'accounts_count': count}
        )


def check_deposit_then_cashout(user):
    """Detecta recarga seguida de cash-out en ventana de tiempo corta."""
    window_start = timezone.now() - timedelta(minutes=CASHOUT_WINDOW_MINUTES)

    recent_deposit = LedgerEntry.objects.filter(
        user=user,
        account_type=AccountType.USER_WALLET,
        direction=Direction.CREDIT,
        description__icontains='Recarga',
        created_at__gte=window_start,
    ).exists()

    recent_cashout = LedgerEntry.objects.filter(
        user=user,
        account_type=AccountType.USER_WALLET,
        direction=Direction.CREDIT,
        description__icontains='Cash-out',
        created_at__gte=window_start,
    ).exists()

    if recent_deposit and recent_cashout:
        _create_alert(
            user=user,
            activity_type=FraudRuleType.DEPOSIT_THEN_CASHOUT,
            severity=AlertSeverity.MEDIUM,
            reason=f"Usuario realizó recarga y cash-out en menos de {CASHOUT_WINDOW_MINUTES} minutos.",
            metadata={'window_minutes': CASHOUT_WINDOW_MINUTES}
        )


def check_identical_bet_pattern(bet):
    """Detecta si varios usuarios hacen apuestas idénticas en un intervalo corto."""
    from apps.betting.models import Bet, BetStatus
    
    window_start = timezone.now() - timedelta(minutes=IDENTICAL_BET_WINDOW_MINUTES)
    
    # Buscar apuestas exactas recientes
    identical_bets = Bet.objects.filter(
        selection_id=bet.selection_id,
        stake=bet.stake,
        odds_at_placement=bet.odds_at_placement,
        placed_at__gte=window_start,
        status__in=[BetStatus.ACCEPTED, BetStatus.PENDING, BetStatus.OPEN, BetStatus.IN_PLAY]
    ).select_related('user')
    
    user_ids = set(identical_bets.values_list('user_id', flat=True))
    
    if len(user_ids) >= IDENTICAL_BET_THRESHOLD:
        # Create alert for the user who triggered the threshold
        event_str = f"{bet.selection.market.event.home_team} vs {bet.selection.market.event.away_team}"
        _create_alert(
            user=bet.user,
            activity_type=FraudRuleType.IDENTICAL_BET_PATTERN,
            severity=AlertSeverity.HIGH,
            reason=(
                f"{len(user_ids)} usuarios apostaron el mismo monto a {event_str}, "
                f"selección {bet.selection.name}, en menos de {IDENTICAL_BET_WINDOW_MINUTES} minutos."
            ),
            metadata={
                'event': event_str,
                'selection_id': bet.selection_id,
                'stake': str(bet.stake),
                'users_count': len(user_ids),
                'users_involved': list(user_ids)
            }
        )


def check_opposite_bets_hedging(user, event_id):
    """Detecta si un usuario intenta cubrir resultados contrarios del mismo evento."""
    from apps.betting.models import Bet, BetStatus
    
    bets_on_event = Bet.objects.filter(
        user=user,
        selection__market__event_id=event_id,
        status__in=[BetStatus.ACCEPTED, BetStatus.PENDING, BetStatus.OPEN, BetStatus.IN_PLAY]
    ).select_related('selection', 'selection__market')

    market_selections = {}
    for b in bets_on_event:
        m_id = b.selection.market_id
        if m_id not in market_selections:
            market_selections[m_id] = {'type': b.selection.market.market_type, 'selections': set()}
        market_selections[m_id]['selections'].add(b.selection.name.lower())

    for m_id, data in market_selections.items():
        m_type = data['type']
        sels = data['selections']
        
        is_hedging = False
        if m_type == '1x2' and len(sels) >= 2:
            is_hedging = True
        elif m_type == 'over_under' and len(sels) >= 2:
            is_hedging = True
        elif m_type == 'btts' and len(sels) >= 2:
            is_hedging = True
            
        if is_hedging:
            _create_alert(
                user=user,
                activity_type=FraudRuleType.OPPOSITE_BETS_HEDGING,
                severity=AlertSeverity.MEDIUM,
                reason=f"Usuario cubrió múltiples resultados del mismo evento (Mercado {m_type}).",
                metadata={'event_id': event_id, 'market_id': m_id, 'selections': list(sels)}
            )
            break  # one alert per event check is enough

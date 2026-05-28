from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import SuspiciousActivity, FraudRuleType
from apps.wallet.models import LedgerEntry, AccountType, Direction

SAME_IP_THRESHOLD = 3
CASHOUT_WINDOW_MINUTES = 30


def check_same_ip(user, ip_address: str):
    """Detecta si la misma IP se usa con N+ cuentas distintas."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    count = User.objects.filter(
        last_login_ip=ip_address
    ).exclude(id=user.id).count()

    if count >= SAME_IP_THRESHOLD:
        SuspiciousActivity.objects.create(
            rule_type=FraudRuleType.SAME_IP_MULTIPLE_ACCOUNTS,
            user=user,
            ip_address=ip_address,
            description=f"IP {ip_address} usada por {count + 1} cuentas",
            metadata={'ip': ip_address, 'count': count + 1},
        )


def check_deposit_then_cashout(user):
    """Detecta depósito seguido de cash-out en ventana de tiempo corta."""
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
        SuspiciousActivity.objects.create(
            rule_type=FraudRuleType.DEPOSIT_THEN_CASHOUT,
            user=user,
            description=f"Depósito seguido de cash-out en {CASHOUT_WINDOW_MINUTES} min",
            metadata={'window_minutes': CASHOUT_WINDOW_MINUTES},
        )


def check_identical_bet_pattern(user):
    """Detecta patrones de apuestas idénticas en grupo."""
    from apps.betting.models import Bet, BetStatus
    recent_bets = Bet.objects.filter(
        user=user,
        status__in=[BetStatus.ACCEPTED, BetStatus.SETTLED],
        placed_at__gte=timezone.now() - timedelta(hours=1),
    )
    if recent_bets.count() >= 10:
        # Buscar si otros usuarios hicieron exactamente las mismas apuestas
        from django.contrib.auth import get_user_model
        User = get_user_model()
        selections = set(recent_bets.values_list('selection_id', flat=True))

        for other_user in User.objects.exclude(id=user.id):
            other_bets = Bet.objects.filter(
                user=other_user,
                selection_id__in=selections,
                placed_at__gte=timezone.now() - timedelta(hours=1),
            )
            overlap = other_bets.count()
            if overlap >= len(selections) * 0.8:
                SuspiciousActivity.objects.create(
                    rule_type=FraudRuleType.IDENTICAL_BET_PATTERN,
                    user=user,
                    description=(
                        f"Patrón de apuestas 80%+ idéntico con {other_user.username} "
                        f"({overlap}/{len(selections)} selecciones)"
                    ),
                    metadata={
                        'other_user': other_user.username,
                        'overlap': overlap,
                        'total': len(selections),
                    },
                )

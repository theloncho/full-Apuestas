import pytest
from decimal import Decimal


@pytest.fixture
def verified_user(db):
    """Crea un usuario verificado para pruebas."""
    from apps.users.models import User, AccountStatus
    user = User.objects.create_user(
        username='testuser',
        password='TestPass123!',
        email='test@test.com',
        dni='72345678',
        birth_date='1995-01-15',
        account_status=AccountStatus.VERIFIED,
    )
    return user


@pytest.fixture
def funded_user(verified_user):
    """Crea un usuario verificado con fichas en su wallet.
    El bono de bienvenida se cancela para aislar pruebas que no testean bonos.
    """
    from apps.wallet.models import WalletService, UserBonus, BonusStatus
    from apps.wallet.models import LedgerEntry
    # Usar direct LedgerEntry para no disparar el bono de bienvenida en tests de wallet puro
    import uuid
    from apps.wallet.models import AccountType, Direction
    tid = uuid.uuid4()
    LedgerEntry.objects.create(
        account_type=AccountType.HOUSE, user=None, amount=Decimal('1000'),
        direction=Direction.DEBIT, transaction_id=tid, description='Fichas de prueba'
    )
    LedgerEntry.objects.create(
        account_type=AccountType.USER_WALLET, user=verified_user, amount=Decimal('1000'),
        direction=Direction.CREDIT, transaction_id=tid, description='Fichas de prueba'
    )
    return verified_user


@pytest.fixture
def event_with_market(db):
    """Crea un evento con mercado 1X2 y selecciones."""
    from apps.betting.models import Sport, Event, Market, Selection, MarketType
    from django.utils import timezone
    from datetime import timedelta

    sport = Sport.objects.create(name='Fútbol', slug='futbol-test')
    event = Event.objects.create(
        sport=sport,
        home_team='Perú',
        away_team='Brasil',
        scheduled_at=timezone.now() + timedelta(hours=2),
    )
    market = Market.objects.create(event=event, market_type=MarketType.HOME_DRAW_AWAY)
    sel_1 = Selection.objects.create(market=market, name='1', odds=Decimal('2.50'))
    sel_x = Selection.objects.create(market=market, name='X', odds=Decimal('3.20'))
    sel_2 = Selection.objects.create(market=market, name='2', odds=Decimal('3.00'))

    return {
        'event': event,
        'market': market,
        'selections': {'1': sel_1, 'X': sel_x, '2': sel_2},
    }

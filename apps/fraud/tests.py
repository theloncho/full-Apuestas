from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import uuid
from decimal import Decimal

from apps.fraud.models import SuspiciousActivity, FraudRuleType, AlertSeverity
from apps.fraud.detectors import (
    check_same_ip, 
    check_deposit_then_cashout, 
    check_identical_bet_pattern, 
    check_opposite_bets_hedging
)
from apps.wallet.models import LedgerEntry, AccountType, Direction
from apps.betting.models import Sport, Event, Market, MarketType, Selection, Bet, BetStatus

User = get_user_model()

class FraudDetectorsTestCase(TestCase):
    def setUp(self):
        # Create base data for betting tests
        self.sport = Sport.objects.create(name="Football")
        self.event = Event.objects.create(
            sport=self.sport,
            home_team="Team A",
            away_team="Team B",
            scheduled_at=timezone.now() + timedelta(days=1)
        )
        self.market_1x2 = Market.objects.create(
            event=self.event,
            market_type='1X2'
        )
        self.sel_1 = Selection.objects.create(market=self.market_1x2, name="1", odds=Decimal('2.00'))
        self.sel_x = Selection.objects.create(market=self.market_1x2, name="x", odds=Decimal('3.00'))
        self.sel_2 = Selection.objects.create(market=self.market_1x2, name="2", odds=Decimal('4.00'))

    def test_check_same_ip(self):
        """Test 1: Misma IP con varias cuentas."""
        ip = "192.168.1.100"
        for i in range(5):
            u = User.objects.create(username=f"ip_user_{i}", birth_date="1990-01-01", dni=f"1111111{i}")
            u.last_login_ip = ip
            u.save()
        
        main_user = User.objects.first()
        check_same_ip(main_user, ip)
        
        alert = SuspiciousActivity.objects.filter(activity_type=FraudRuleType.SAME_IP_MULTIPLE_ACCOUNTS).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.HIGH)
        self.assertIn("usada por 5 cuentas", alert.reason)

    def test_check_deposit_then_cashout(self):
        """Test 2: Depósito seguido de Cash-out rápido."""
        user = User.objects.create(username="depositor", birth_date="1990-01-01", dni="22222222")
        
        # Simulate recent deposit
        LedgerEntry.objects.create(
            user=user,
            account_type=AccountType.USER_WALLET,
            direction=Direction.CREDIT,
            amount=Decimal('100.00'),
            description="Recarga de fichas",
            transaction_id=str(uuid.uuid4()),
        )
        
        # Simulate recent cashout (Early bet closure)
        LedgerEntry.objects.create(
            user=user,
            account_type=AccountType.USER_WALLET,
            direction=Direction.CREDIT,
            amount=Decimal('50.00'),
            description="Cash-out de apuesta",
            transaction_id=str(uuid.uuid4()),
        )
        
        check_deposit_then_cashout(user)
        alert = SuspiciousActivity.objects.filter(activity_type=FraudRuleType.DEPOSIT_THEN_CASHOUT).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.MEDIUM)

    def test_check_identical_bet_pattern(self):
        """Test 3: Patrón de apuestas idénticas en grupo (Colusión)."""
        # Create 4 users placing the exact same bet
        users = [User.objects.create(username=f"colusion_user_{i}", birth_date="1990-01-01", dni=f"3333333{i}") for i in range(4)]
        last_bet = None
        
        for u in users:
            last_bet = Bet.objects.create(
                user=u,
                selection=self.sel_1,
                stake=Decimal('100.00'),
                odds_at_placement=Decimal('2.00'),
                status=BetStatus.ACCEPTED,
                bet_id=f"BET-{u.id}"
            )
            # Override created_at to be very recent
            last_bet.placed_at = timezone.now()
            last_bet.save()
            
        # Trigger detector with the last placed bet
        check_identical_bet_pattern(last_bet)
        
        alert = SuspiciousActivity.objects.filter(activity_type=FraudRuleType.IDENTICAL_BET_PATTERN).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.HIGH)
        self.assertIn("4 usuarios apostaron el mismo monto", alert.reason)

    def test_check_opposite_bets_hedging(self):
        """Test 4: Cobertura de resultados opuestos en el mismo partido."""
        user = User.objects.create(username="hedger", birth_date="1990-01-01", dni="44444444")
        
        # User bets on Home (1)
        Bet.objects.create(
            user=user,
            selection=self.sel_1,
            stake=Decimal('10.00'),
            odds_at_placement=Decimal('2.00'),
            status=BetStatus.ACCEPTED,
            bet_id="BET-H1"
        )
        
        # User bets on Away (2) to hedge
        Bet.objects.create(
            user=user,
            selection=self.sel_2,
            stake=Decimal('10.00'),
            odds_at_placement=Decimal('4.00'),
            status=BetStatus.ACCEPTED,
            bet_id="BET-H2"
        )
        
        check_opposite_bets_hedging(user, self.event.id)
        
        alert = SuspiciousActivity.objects.filter(activity_type=FraudRuleType.OPPOSITE_BETS_HEDGING).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.MEDIUM)

    def test_prevent_duplicate_alerts(self):
        """Test 5: No generar alertas duplicadas."""
        user = User.objects.create(username="spammer", birth_date="1990-01-01", dni="55555555")
        ip = "10.0.0.1"
        
        # Create threshold
        for i in range(5):
            u = User.objects.create(username=f"spam_user_{i}", birth_date="1990-01-01", dni=f"6666666{i}")
            u.last_login_ip = ip
            u.save()
            
        # Trigger detector first time
        check_same_ip(user, ip)
        self.assertEqual(SuspiciousActivity.objects.filter(user=user).count(), 1)
        
        # Trigger detector second time immediately
        check_same_ip(user, ip)
        # Should still be 1, because it prevents spamming
        self.assertEqual(SuspiciousActivity.objects.filter(user=user).count(), 1)

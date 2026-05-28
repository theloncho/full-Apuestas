"""
Tests de betting — FSM, liquidación y validaciones.
"""
import pytest
from decimal import Decimal
from django.db.models import Sum, Q

from apps.betting.models import Bet, BetStatus, EventStatus
from apps.betting.services import LiquidationService
from apps.wallet.models import WalletService, LedgerEntry, Direction


@pytest.mark.django_db
class TestBetFSM:
    def test_bet_accept_locks_funds(self, funded_user, event_with_market):
        sel = event_with_market['selections']['1']
        bet = Bet.objects.create(
            user=funded_user,
            selection=sel,
            stake=Decimal('100'),
            odds_at_placement=sel.odds,
        )
        bet.accept()
        bet.save()

        assert bet.status == BetStatus.ACCEPTED
        balance = WalletService.get_balance(funded_user)
        assert balance == Decimal('900')  # 1000 - 100

    def test_bet_lifecycle_won(self, funded_user, event_with_market):
        sel = event_with_market['selections']['1']
        bet = Bet.objects.create(
            user=funded_user,
            selection=sel,
            stake=Decimal('100'),
            odds_at_placement=sel.odds,
        )
        bet.accept()
        bet.save()

        bet.start_settling()
        bet.save()
        assert bet.status == BetStatus.SETTLING

        sel.is_winner = True
        sel.save()

        bet.mark_won()
        bet.save()
        assert bet.status == BetStatus.WON
        assert bet.payout == Decimal('250.0000')  # 100 * 2.50

        bet.settle()
        bet.save()
        assert bet.status == BetStatus.SETTLED

    def test_bet_lifecycle_lost(self, funded_user, event_with_market):
        sel = event_with_market['selections']['1']
        bet = Bet.objects.create(
            user=funded_user,
            selection=sel,
            stake=Decimal('100'),
            odds_at_placement=sel.odds,
        )
        bet.accept()
        bet.save()

        bet.start_settling()
        bet.mark_lost()
        bet.settle()
        bet.save()

        assert bet.status == BetStatus.SETTLED
        assert bet.payout == Decimal('0')

    def test_bet_cashout(self, funded_user, event_with_market):
        sel = event_with_market['selections']['1']
        bet = Bet.objects.create(
            user=funded_user,
            selection=sel,
            stake=Decimal('100'),
            odds_at_placement=sel.odds,
        )
        bet.accept()
        bet.save()

        cashout = bet.calculated_cashout
        assert cashout > Decimal('0')

        bet.cash_out(cashout)
        bet.settle()
        bet.save()

        assert bet.status == BetStatus.SETTLED
        assert bet.cashout_amount == cashout

    def test_bet_void_returns_stake(self, funded_user, event_with_market):
        sel = event_with_market['selections']['1']
        bet = Bet.objects.create(
            user=funded_user,
            selection=sel,
            stake=Decimal('100'),
            odds_at_placement=sel.odds,
        )
        bet.accept()
        bet.save()

        bet.void_bet()
        bet.settle()
        bet.save()

        balance = WalletService.get_balance(funded_user)
        assert balance == Decimal('1000')  # Fully returned

    def test_insufficient_balance_rejects(self, funded_user, event_with_market):
        sel = event_with_market['selections']['1']
        bet = Bet.objects.create(
            user=funded_user,
            selection=sel,
            stake=Decimal('2000'),  # More than 1000
            odds_at_placement=sel.odds,
        )
        with pytest.raises(ValueError, match='Saldo insuficiente'):
            bet.accept()


@pytest.mark.django_db
class TestLiquidation:
    def test_liquidate_event_resolves_bets(self, funded_user, event_with_market):
        sel_1 = event_with_market['selections']['1']
        sel_x = event_with_market['selections']['X']
        event = event_with_market['event']

        # User bets on '1' (local wins)
        bet_1 = Bet.objects.create(
            user=funded_user, selection=sel_1,
            stake=Decimal('50'), odds_at_placement=sel_1.odds,
        )
        bet_1.accept()
        bet_1.save()

        # Liquidate: home wins 2-1
        LiquidationService.liquidate_event(event, 2, 1)

        bet_1.refresh_from_db()
        # After liquidation the bet goes through won -> settled cycle
        assert bet_1.status in (BetStatus.SETTLED, BetStatus.WON)
        assert bet_1.payout == (Decimal('50') * Decimal('2.5')).quantize(Decimal('0.0001'))

        # Ledger stays balanced
        credits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.CREDIT))
        )['total'] or Decimal('0')
        debits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.DEBIT))
        )['total'] or Decimal('0')
        assert credits == debits


@pytest.mark.django_db
class TestBetValidators:
    def test_validate_combined_same_market_raises(self, event_with_market):
        from apps.betting.validators import validate_combined_bet_selections
        sel_1 = event_with_market['selections']['1']
        sel_x = event_with_market['selections']['X']

        with pytest.raises(ValueError, match='No puedes combinar'):
            validate_combined_bet_selections([sel_1, sel_x])

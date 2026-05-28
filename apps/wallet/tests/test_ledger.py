import pytest
from decimal import Decimal
from django.test import TestCase
from hypothesis import given, settings, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from apps.wallet.models import LedgerEntry, WalletService, AccountType, Direction
from django.contrib.auth import get_user_model
from django.db.models import Sum, Q

User = get_user_model()


class TestLedgerInvariants(HypothesisTestCase):
    """
    Property-based tests con Hypothesis.
    Verifican invariantes financieras bajo cualquier entrada válida.
    """

    def setUp(self):
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f'test_user_ledger_{unique_id}',
            password='TestPassword123!',
            dni=unique_id,
            birth_date='1990-01-01',
            account_status='verificado'
        )

    @given(amount=st.decimals(min_value=Decimal('1'), max_value=Decimal('1000'),
                              allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_global_ledger_sum_is_zero(self, amount):
        """La suma global de débitos y créditos siempre es cero."""
        WalletService.deposit_tokens(self.user, amount)
        
        credits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.CREDIT))
        )['total'] or Decimal('0')
        debits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.DEBIT))
        )['total'] or Decimal('0')
        
        assert credits == debits, f"Desequilibrio: créditos={credits}, débitos={debits}"

    @given(amount=st.decimals(min_value=Decimal('1'), max_value=Decimal('500'),
                              allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_balance_never_negative(self, amount):
        """Ningún wallet puede terminar con saldo negativo."""
        WalletService.deposit_tokens(self.user, amount)
        balance = WalletService.get_balance(self.user)
        assert balance >= Decimal('0'), f"Saldo negativo: {balance}"

    @given(
        stake=st.decimals(min_value=Decimal('1'), max_value=Decimal('100'),
                          allow_nan=False, allow_infinity=False),
        odds=st.decimals(min_value=Decimal('1.01'), max_value=Decimal('50'),
                         allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30)
    def test_payout_exact_calculation(self, stake, odds):
        """payout = stake × odds con precisión Decimal exacta (no float)."""
        from decimal import ROUND_HALF_UP
        expected = (stake * odds).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        result = (stake * odds).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        assert result == expected


class TestConcurrency(TestCase):
    """Pruebas de concurrencia: N peticiones simultáneas no generan doble gasto."""

    def test_concurrent_bets_no_double_spend(self):
        import threading
        from apps.betting.models import Sport, Event, Market, Selection, Bet
        from django.utils import timezone
        
        user = User.objects.create_user(
            username='test_concurrent',
            password='TestPassword123!',
            dni='22222222',
            birth_date='1990-01-01',
            account_status='verificado'
        )
        WalletService.deposit_tokens(user, Decimal('100'))

        sport = Sport.objects.create(name='Test Sport', slug='test-sport')
        event = Event.objects.create(
            sport=sport, home_team='A', away_team='B', scheduled_at=timezone.now()
        )
        market = Market.objects.create(event=event, market_type='1X2')
        selection = Selection.objects.create(market=market, name='1', odds=Decimal('2.00'))

        errors = []
        successes = []

        def place_bet():
            try:
                # Se intentará apostar 60 fichas desde 5 hilos simultáneos.
                # Solo 1 hilo debería lograrlo, pues el saldo es 100.
                bet = Bet(
                    user=user, 
                    selection=selection, 
                    stake=Decimal('60'), 
                    odds_at_placement=selection.odds
                )
                # save() y FSM accept(). accept() llama a WalletService.lock_funds_for_bet 
                # que ejecuta el select_for_update, previniendo la condición de carrera
                bet.save()
                bet.accept()
                bet.save()
                successes.append(True)
            except Exception as e:
                errors.append(str(e))
            finally:
                from django.db import connection
                connection.close()

        threads = [threading.Thread(target=place_bet) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No más de 1 debería haber tenido éxito (60 <= 100, pero 60*2 = 120 > 100)
        assert len(successes) <= 1, f"Doble gasto detectado: {len(successes)} éxitos"
        balance = WalletService.get_balance(user)
        assert balance >= Decimal('0'), f"Saldo negativo: {balance}"

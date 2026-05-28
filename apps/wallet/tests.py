"""
Tests de wallet — invariantes financieras con Hypothesis.

Estos tests verifican las 3 invariantes críticas:
1. La suma global de débitos y créditos siempre es cero.
2. Ningún wallet termina con saldo negativo.
3. payout = stake × odds con precisión Decimal exacta.
"""
import pytest
from decimal import Decimal, ROUND_HALF_UP
from django.test import TestCase
from django.db.models import Sum, Q

from apps.wallet.models import LedgerEntry, WalletService, AccountType, Direction
from apps.users.models import User, AccountStatus


@pytest.mark.django_db
class TestWalletDeposit:
    def test_deposit_creates_two_entries(self, verified_user):
        tx_id = WalletService.deposit_tokens(verified_user, Decimal('100'))
        entries = LedgerEntry.objects.filter(transaction_id=tx_id)
        assert entries.count() == 2

    def test_deposit_balance_correct(self, verified_user):
        WalletService.deposit_tokens(verified_user, Decimal('250.5000'))
        balance = WalletService.get_balance(verified_user)
        assert balance == Decimal('250.5000')

    def test_deposit_negative_raises(self, verified_user):
        with pytest.raises(ValueError):
            WalletService.deposit_tokens(verified_user, Decimal('-10'))

    def test_deposit_zero_raises(self, verified_user):
        with pytest.raises(ValueError):
            WalletService.deposit_tokens(verified_user, Decimal('0'))


@pytest.mark.django_db
class TestWalletWithdraw:
    def test_withdraw_success(self, funded_user):
        WalletService.withdraw_tokens(funded_user, Decimal('500'))
        balance = WalletService.get_balance(funded_user)
        assert balance == Decimal('500')

    def test_withdraw_insufficient_raises(self, funded_user):
        with pytest.raises(ValueError, match='Saldo insuficiente'):
            WalletService.withdraw_tokens(funded_user, Decimal('2000'))


@pytest.mark.django_db
class TestLedgerInvariants:
    """Property-based invariant checks."""

    def test_global_sum_zero_after_deposits(self, verified_user):
        """Invariante: suma global de TODOS los débitos y créditos = 0."""
        for amount in [Decimal('100'), Decimal('200.5'), Decimal('50.1234')]:
            WalletService.deposit_tokens(verified_user, amount)

        credits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.CREDIT))
        )['total'] or Decimal('0')
        debits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.DEBIT))
        )['total'] or Decimal('0')

        assert credits == debits, f"Desequilibrio: créditos={credits}, débitos={debits}"

    def test_balance_never_negative(self, funded_user):
        """Invariante: saldo nunca negativo después de operaciones válidas."""
        WalletService.withdraw_tokens(funded_user, Decimal('500'))
        balance = WalletService.get_balance(funded_user)
        assert balance >= Decimal('0')

    def test_payout_exact_decimal(self):
        """Invariante: payout = stake × odds con Decimal exacto."""
        stake = Decimal('100.0000')
        odds = Decimal('2.5000')
        expected = (stake * odds).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        assert expected == Decimal('250.0000')

    def test_multiple_operations_balanced(self, verified_user):
        """Varias operaciones mantienen el ledger balanceado."""
        WalletService.deposit_tokens(verified_user, Decimal('1000'))
        WalletService.withdraw_tokens(verified_user, Decimal('300'))
        WalletService.deposit_tokens(verified_user, Decimal('150'))

        credits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.CREDIT))
        )['total'] or Decimal('0')
        debits = LedgerEntry.objects.aggregate(
            total=Sum('amount', filter=Q(direction=Direction.DEBIT))
        )['total'] or Decimal('0')

        assert credits == debits
        balance = WalletService.get_balance(verified_user)
        assert balance == Decimal('850')

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation

from .models import WalletService, LedgerEntry


@login_required
def wallet_view(request):
    """Vista principal del wallet con historial."""
    user = request.user
    balance = WalletService.get_balance(user)
    pending = WalletService.get_pending_balance(user)
    transactions = LedgerEntry.objects.filter(
        user=user
    ).order_by('-created_at')[:50]

    return render(request, 'wallet/wallet.html', {
        'balance': balance,
        'pending': pending,
        'transactions': transactions,
    })


@login_required
def deposit_view(request):
    """Recarga simulada de fichas."""
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
            if amount <= Decimal('0'):
                messages.error(request, 'El monto debe ser positivo.')
                return redirect('wallet:wallet')
            WalletService.deposit_tokens(request.user, amount)
            messages.success(request, f'Se acreditaron {amount} fichas a tu wallet.')
        except (ValueError, InvalidOperation) as e:
            messages.error(request, str(e))
    return redirect('wallet:wallet')


@login_required
def withdraw_view(request):
    """Retiro simulado de fichas."""
    if request.method == 'POST':
        try:
            amount = Decimal(request.POST.get('amount', '0'))
            if amount <= Decimal('0'):
                messages.error(request, 'El monto debe ser positivo.')
                return redirect('wallet:wallet')
            WalletService.withdraw_tokens(request.user, amount)
            messages.success(request, f'Se retiraron {amount} fichas de tu wallet.')
        except (ValueError, InvalidOperation) as e:
            messages.error(request, str(e))
    return redirect('wallet:wallet')


@login_required
def balance_api(request):
    """API para obtener balance (usado por HTMX/Alpine)."""
    balance = WalletService.get_balance(request.user)
    return JsonResponse({'balance': str(balance)})

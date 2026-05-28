from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Event, EventStatus, Selection, Bet, BetStatus, Market
from .validators import validate_bet_placement
from apps.wallet.models import WalletService


def event_list(request):
    """Lista de eventos deportivos disponibles."""
    now = timezone.now()
    upcoming = Event.objects.filter(
        status__in=[EventStatus.SCHEDULED, EventStatus.LIVE],
    ).select_related('sport').prefetch_related(
        'markets__selections'
    ).order_by('scheduled_at')

    finished = Event.objects.filter(
        status=EventStatus.FINISHED,
    ).select_related('sport').order_by('-scheduled_at')[:10]

    balance = None
    if request.user.is_authenticated:
        balance = WalletService.get_balance(request.user)

    return render(request, 'betting/event_list.html', {
        'upcoming': upcoming,
        'finished': finished,
        'balance': balance,
        'now': now,
    })


def event_detail(request, event_id):
    """Detalle de un evento con todos sus mercados y selecciones."""
    event = get_object_or_404(
        Event.objects.prefetch_related('markets__selections'),
        id=event_id,
    )
    balance = None
    if request.user.is_authenticated:
        balance = WalletService.get_balance(request.user)

    return render(request, 'betting/event_detail.html', {
        'event': event,
        'balance': balance,
    })


@login_required
def place_bet_form(request, selection_id):
    """Formulario para colocar apuesta en una selección."""
    selection = get_object_or_404(
        Selection.objects.select_related('market__event'),
        id=selection_id,
    )
    event = selection.market.event
    balance = WalletService.get_balance(request.user)

    return render(request, 'betting/place_bet.html', {
        'selection': selection,
        'event': event,
        'balance': balance,
    })


@login_required
@transaction.atomic
def place_bet(request):
    """Procesa la apuesta (POST)."""
    if request.method != 'POST':
        return redirect('betting:event_list')

    try:
        selection_id = int(request.POST.get('selection_id'))
        stake = Decimal(request.POST.get('stake', '0'))
        odds_confirmed = Decimal(request.POST.get('odds_confirmed', '0'))
    except (ValueError, InvalidOperation, TypeError):
        messages.error(request, 'Datos inválidos.')
        return redirect('betting:event_list')

    selection = get_object_or_404(
        Selection.objects.select_related('market__event'),
        id=selection_id,
    )
    market = selection.market
    event = market.event

    # Re-cotización: verificar que las odds no hayan cambiado
    selection_odds_rounded = selection.odds.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if odds_confirmed != selection_odds_rounded:
        messages.warning(
            request,
            f'La cuota cambió de {odds_confirmed} a {selection_odds_rounded}. '
            f'Por favor, confirma con la nueva cuota.'
        )
        return redirect('betting:place_bet_form', selection_id=selection.id)

    # Validar apuesta
    errors = validate_bet_placement(request.user, selection, stake, market)
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect('betting:place_bet_form', selection_id=selection.id)

    # Crear y aceptar apuesta
    try:
        bet = Bet(
            user=request.user,
            selection=selection,
            stake=stake,
            odds_at_placement=selection.odds,
        )
        bet.save()
        bet.accept()
        bet.save()
        messages.success(
            request,
            f'Apuesta colocada: {stake} fichas en "{selection.name}" @ {selection.odds}. '
            f'Ganancia potencial: {(stake * selection.odds).quantize(Decimal("0.01"))} fichas.'
        )
        
        # Enviar actualización en tiempo real al dashboard del admin
        channel_layer = get_channel_layer()
        event_name = f"{event.home_team} vs {event.away_team}"
        print(f"WS Broadcasting new bet: {bet.id}")
        async_to_sync(channel_layer.group_send)(
            "dashboard_group",
            {
                "type": "dashboard_update",
                "message": {
                    "event": "new_bet",
                    "data": {
                        "id": str(bet.id),
                        "user": request.user.username,
                        "event_name": event_name,
                        "odds": str(bet.odds_at_placement),
                        "stake": str(bet.stake),
                        "status_display": bet.get_status_display(),
                        "status": bet.status,
                    }
                }
            }
        )
    except Exception as e:
        messages.error(request, f'Error al colocar apuesta: {str(e)}')

    return redirect('betting:event_list')


@login_required
def bet_history(request):
    """Historial de apuestas del usuario."""
    bets = Bet.objects.filter(
        user=request.user,
    ).select_related(
        'selection__market__event',
    ).order_by('-placed_at')

    balance = WalletService.get_balance(request.user)

    return render(request, 'betting/bet_history.html', {
        'bets': bets,
        'balance': balance,
    })


@login_required
@transaction.atomic
def cashout_bet(request, bet_id):
    """Cash-out de una apuesta aceptada."""
    bet = get_object_or_404(
        Bet.objects.select_related('selection'),
        id=bet_id,
        user=request.user,
    )
    if bet.status != BetStatus.ACCEPTED:
        messages.error(request, 'Solo puedes hacer cash-out de apuestas aceptadas.')
        return redirect('betting:bet_history')

    cashout_amount = bet.calculated_cashout
    if cashout_amount <= Decimal('0'):
        messages.error(request, 'Cash-out no disponible para esta apuesta.')
        return redirect('betting:bet_history')

    try:
        bet.cash_out(cashout_amount)
        bet.settle()
        bet.save()
        messages.success(
            request,
            f'Cash-out exitoso: {cashout_amount} fichas acreditadas a tu wallet.'
        )
    except Exception as e:
        messages.error(request, f'Error en cash-out: {str(e)}')

    return redirect('betting:bet_history')

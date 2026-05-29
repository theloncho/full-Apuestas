from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Event, EventStatus, Selection, Bet, BetStatus, Market, CombinedBet
from .validators import validate_bet_placement, validate_combined_bet_placement
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
    """Procesa la apuesta (POST).
    
    Si la petición es AJAX (X-Requested-With: XMLHttpRequest) responde con JSON.
    Si no, redirige (comportamiento clásico).
    """
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if request.method != 'POST':
        if ajax:
            return JsonResponse({'success': False, 'error': 'Método no permitido.'})
        return redirect('betting:event_list')

    try:
        selection_id = int(request.POST.get('selection_id'))
        stake = Decimal(request.POST.get('stake', '0'))
        odds_confirmed = Decimal(request.POST.get('odds_confirmed', '0'))
    except (ValueError, InvalidOperation, TypeError):
        if ajax:
            return JsonResponse({'success': False, 'error': 'Datos inválidos.'})
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
        if ajax:
            return JsonResponse({
                'success': False,
                'recotizacion': True,
                'new_odds': str(selection_odds_rounded),
                'error': f'La cuota cambió de {odds_confirmed} a {selection_odds_rounded}. Confirma la nueva cuota.',
            })
        messages.warning(
            request,
            f'La cuota cambió de {odds_confirmed} a {selection_odds_rounded}. '
            f'Por favor, confirma con la nueva cuota.'
        )
        return redirect('betting:place_bet_form', selection_id=selection.id)

    # Validar apuesta
    errors = validate_bet_placement(request.user, selection, stake, market)
    if errors:
        if ajax:
            return JsonResponse({'success': False, 'error': ' '.join(errors)})
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

        # Anti-fraude: verificar patrones sospechosos tras confirmar apuesta
        try:
            from apps.fraud.detectors import check_identical_bet_pattern, check_opposite_bets_hedging
            check_identical_bet_pattern(bet)
            check_opposite_bets_hedging(request.user, event.id)
        except Exception:
            pass  # No bloquear la apuesta por errores del detector

        new_balance = WalletService.get_balance(request.user)

        if ajax:
            return JsonResponse({
                'success': True,
                'bet_id': bet.bet_id,
                'bet_uuid': str(bet.id),
                'new_balance': str(new_balance),
                'message': f'Apuesta #{bet.bet_id} colocada: {stake} fichas en "{selection.name}" @ {selection.odds}.',
            })

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
                        "bet_id": bet.bet_id,
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
        if ajax:
            return JsonResponse({'success': False, 'error': f'Error al colocar apuesta: {str(e)}'})
        messages.error(request, f'Error al colocar apuesta: {str(e)}')

    return redirect('betting:event_list')


@login_required
def bet_history(request):
    """Historial de apuestas del usuario."""
    filter_type = request.GET.get('filter', 'all')
    
    simple_query = Bet.objects.filter(user=request.user)
    combined_query = CombinedBet.objects.filter(user=request.user)
    
    if filter_type == 'open':
        simple_query = simple_query.filter(status__in=[BetStatus.ACCEPTED, BetStatus.PENDING])
        combined_query = combined_query.filter(status__in=[BetStatus.ACCEPTED, BetStatus.PENDING])
    elif filter_type == 'resolved':
        simple_query = simple_query.filter(status=BetStatus.SETTLED)
        combined_query = combined_query.filter(status=BetStatus.SETTLED)
    elif filter_type == 'won':
        simple_query = simple_query.filter(status=BetStatus.SETTLED, payout__gt=0, cashout_amount__isnull=True)
        combined_query = combined_query.filter(status=BetStatus.SETTLED, payout__gt=0, cashout_amount__isnull=True)
    elif filter_type == 'lost':
        simple_query = simple_query.filter(status=BetStatus.SETTLED, payout=0, cashout_amount__isnull=True)
        combined_query = combined_query.filter(status=BetStatus.SETTLED, payout=0, cashout_amount__isnull=True)

    simple_bets = list(simple_query.select_related('selection__market__event'))
    for b in simple_bets:
        b.is_combined = False

    combined_bets = list(combined_query.prefetch_related('selections__market__event'))
    for cb in combined_bets:
        cb.is_combined = True

    all_bets = simple_bets + combined_bets
    all_bets.sort(key=lambda x: x.placed_at, reverse=True)

    balance = WalletService.get_balance(request.user)

    return render(request, 'betting/bet_history.html', {
        'bets': all_bets,
        'balance': balance,
        'current_filter': filter_type,
    })


@login_required
def bet_search(request):
    """AJAX: Busca una apuesta por bet_id."""
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'found': False, 'error': 'Ingrese un ID de apuesta.'})
    try:
        bet = Bet.objects.select_related(
            'selection__market__event', 'user'
        ).get(bet_id=q, user=request.user)
        return JsonResponse({
            'found': True,
            'bet_id': bet.bet_id,
            'event': f'{bet.selection.market.event.home_team} vs {bet.selection.market.event.away_team}',
            'odds': str(bet.odds_at_placement),
            'stake': str(bet.stake),
            'payout': str(bet.potential_payout),
            'status': bet.status,
            'status_display': bet.get_status_display(),
            'placed_at': bet.placed_at.strftime('%d/%m/%Y %H:%M'),
        })
    except Bet.DoesNotExist:
        try:
            cbet = CombinedBet.objects.prefetch_related(
                'selections__market__event', 'user'
            ).get(bet_id=q, user=request.user)
            return JsonResponse({
                'found': True,
                'bet_id': cbet.bet_id,
                'event': f'Combinada ({cbet.selections.count()} selecciones)',
                'odds': str(cbet.combined_odds),
                'stake': str(cbet.stake),
                'payout': str(cbet.potential_payout),
                'status': cbet.status,
                'status_display': cbet.get_status_display(),
                'placed_at': cbet.placed_at.strftime('%d/%m/%Y %H:%M'),
            })
        except CombinedBet.DoesNotExist:
            return JsonResponse({'found': False, 'error': f'No se encontró la apuesta con ID "{q}".'})


@login_required
@transaction.atomic
def place_combined_bet(request):
    """AJAX: coloca una apuesta combinada."""
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Solo AJAX.'}, status=400)

    try:
        selection_ids = request.POST.getlist('selection_ids[]') or request.POST.getlist('selection_ids')
        stake = Decimal(request.POST.get('stake', '0'))
        odds_confirmed_raw = request.POST.get('odds_confirmed', '')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Datos inválidos.'})

    selections = list(Selection.objects.select_related('market__event').filter(id__in=selection_ids))
    if len(selections) < 2:
        return JsonResponse({'success': False, 'error': 'Se necesitan al menos 2 selecciones.'})

    # Validar
    errors = validate_combined_bet_placement(request.user, selections, stake)
    if errors:
        return JsonResponse({'success': False, 'error': ' '.join(errors)})

    # Calcular cuota combinada actual
    combined_odds = Decimal('1')
    for sel in selections:
        combined_odds *= sel.odds
    combined_odds = combined_odds.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    # Re-cotización si las cuotas cambiaron
    if odds_confirmed_raw:
        odds_confirmed = Decimal(odds_confirmed_raw).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        if odds_confirmed != combined_odds:
            return JsonResponse({
                'success': False,
                'recotizacion': True,
                'new_odds': str(combined_odds),
                'error': f'La cuota combinada cambió de {odds_confirmed} a {combined_odds}. Confirma la nueva cuota.',
            })

    # Idempotencia
    idempotency_key = request.POST.get('idempotency_key')
    if idempotency_key:
        try:
            CombinedBet.objects.get(idempotency_key=idempotency_key)
            return JsonResponse({'success': False, 'error': 'Esta apuesta ya fue procesada.'})
        except CombinedBet.DoesNotExist:
            pass

    try:
        combined_bet = CombinedBet(
            user=request.user,
            stake=stake,
            combined_odds=combined_odds,
            status=BetStatus.PENDING,
            idempotency_key=idempotency_key or None,
        )
        combined_bet.save()
        combined_bet.selections.set(selections)
        combined_bet.accept()
        combined_bet.save()

        return JsonResponse({
            'success': True,
            'bet_id': combined_bet.bet_id,
            'bet_uuid': str(combined_bet.id),
            'combined_odds': str(combined_odds),
            'message': f'Combinada #{combined_bet.bet_id} colocada: {stake} fichas @ {combined_odds}.',
        })
    except ValueError as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@transaction.atomic
def cashout_bet(request, bet_id):
    """Cash-out de una apuesta aceptada."""
    from apps.wallet.models import WalletService
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    bet = get_object_or_404(
        Bet.objects.select_related('selection'),
        id=bet_id,
        user=request.user,
    )
    if bet.status != BetStatus.ACCEPTED:
        if ajax:
            return JsonResponse({'success': False, 'error': 'Solo puedes hacer cash-out de apuestas aceptadas.'})
        messages.error(request, 'Solo puedes hacer cash-out de apuestas aceptadas.')
        return redirect('betting:bet_history')

    cashout_amount = bet.calculated_cashout
    if cashout_amount <= Decimal('0'):
        if ajax:
            return JsonResponse({'success': False, 'error': 'Cash-out no disponible para esta apuesta.'})
        messages.error(request, 'Cash-out no disponible para esta apuesta.')
        return redirect('betting:bet_history')

    try:
        bet.cash_out(cashout_amount)
        bet.settle()
        bet.save()

        # Anti-fraude: verificar depósito seguido de cash-out
        try:
            from apps.fraud.detectors import check_deposit_then_cashout
            check_deposit_then_cashout(request.user)
        except Exception:
            pass

        new_balance = WalletService.get_balance(request.user)
        if ajax:
            return JsonResponse({
                'success': True,
                'bet_id': bet.bet_id,
                'cashout_amount': str(cashout_amount),
                'new_balance': str(new_balance),
                'message': f'Cash-out exitoso: {cashout_amount} fichas.',
            })
        messages.success(request, f'Cash-out exitoso: {cashout_amount} fichas acreditadas a tu wallet.')
    except Exception as e:
        if ajax:
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'Error en cash-out: {str(e)}')

    return redirect('betting:bet_history')


@login_required
def bet_history_json(request):
    """AJAX: todas las apuestas (simples + combinadas) del usuario."""
    from decimal import Decimal
    bets = Bet.objects.filter(user=request.user).select_related(
        'selection__market__event',
    ).order_by('-placed_at')

    combined = CombinedBet.objects.filter(
        user=request.user
    ).prefetch_related(
        'selections__market__event',
    ).order_by('-placed_at')

    items = []
    for b in bets:
        items.append({
            'type': 'simple',
            'bet_id': b.bet_id,
            'uuid': str(b.id),
            'event': f'{b.selection.market.event.home_team} vs {b.selection.market.event.away_team}',
            'selection': b.selection.name,
            'market': b.selection.market.get_market_type_display(),
            'odds': str(b.odds_at_placement),
            'stake': str(b.stake),
            'payout': str(b.potential_payout),
            'status': b.status,
            'status_display': b.get_status_display(),
            'placed_at': b.placed_at.strftime('%d/%m/%Y %H:%M'),
            'cashout_available': b.status == BetStatus.ACCEPTED and str(b.calculated_cashout) != '0',
            'cashout_amount': str(b.calculated_cashout) if b.status == BetStatus.ACCEPTED else '0',
        })
    for cb in combined:
        selections_list = []
        for sel in cb.selections.all():
            selections_list.append({
                'name': sel.name,
                'odds': str(sel.odds),
                'event': f'{sel.market.event.home_team} vs {sel.market.event.away_team}',
            })
        items.append({
            'type': 'combinada',
            'bet_id': cb.bet_id,
            'uuid': str(cb.id),
            'selections': selections_list,
            'count': cb.selections.count(),
            'odds': str(cb.combined_odds),
            'stake': str(cb.stake),
            'payout': str(cb.potential_payout),
            'status': cb.status,
            'status_display': cb.get_status_display(),
            'placed_at': cb.placed_at.strftime('%d/%m/%Y %H:%M'),
            'cashout_available': cb.status == BetStatus.ACCEPTED and str(cb.calculated_cashout) != '0',
            'cashout_amount': str(cb.calculated_cashout) if cb.status == BetStatus.ACCEPTED else '0',
        })

    items.sort(key=lambda x: x['placed_at'], reverse=True)
    return JsonResponse({'bets': items})


@login_required
def open_bets_json(request):
    """AJAX: solo apuestas abiertas (simples + combinadas) del usuario."""
    from decimal import Decimal
    from .models import BetStatus

    open_statuses = [BetStatus.ACCEPTED, BetStatus.PENDING]
    # In case other open statuses are added in models or custom DB statuses
    additional_open_statuses = ["accepted", "pending", "open", "in_play"]

    bets = Bet.objects.filter(
        user=request.user,
        status__in=additional_open_statuses
    ).select_related(
        'selection__market__event',
    ).order_by('-placed_at')

    combined = CombinedBet.objects.filter(
        user=request.user,
        status__in=additional_open_statuses
    ).prefetch_related(
        'selections__market__event',
    ).order_by('-placed_at')

    items = []
    for b in bets:
        items.append({
            'type': 'simple',
            'bet_id': b.bet_id,
            'uuid': str(b.id),
            'event': f'{b.selection.market.event.home_team} vs {b.selection.market.event.away_team}',
            'selection': b.selection.name,
            'market': b.selection.market.get_market_type_display(),
            'odds': str(b.odds_at_placement),
            'stake': str(b.stake),
            'payout': str(b.potential_payout),
            'status': b.status,
            'status_display': b.get_status_display(),
            'placed_at': b.placed_at.strftime('%d/%m/%Y %H:%M'),
            'cashout_available': b.status == BetStatus.ACCEPTED and str(b.calculated_cashout) != '0',
            'cashout_amount': str(b.calculated_cashout) if b.status == BetStatus.ACCEPTED else '0',
        })
    for cb in combined:
        selections_list = []
        for sel in cb.selections.all():
            selections_list.append({
                'name': sel.name,
                'odds': str(sel.odds),
                'event': f'{sel.market.event.home_team} vs {sel.market.event.away_team}',
            })
        items.append({
            'type': 'combinada',
            'bet_id': cb.bet_id,
            'uuid': str(cb.id),
            'selections': selections_list,
            'count': cb.selections.count(),
            'odds': str(cb.combined_odds),
            'stake': str(cb.stake),
            'payout': str(cb.potential_payout),
            'status': cb.status,
            'status_display': cb.get_status_display(),
            'placed_at': cb.placed_at.strftime('%d/%m/%Y %H:%M'),
            'cashout_available': cb.status == BetStatus.ACCEPTED and str(cb.calculated_cashout) != '0',
            'cashout_amount': str(cb.calculated_cashout) if cb.status == BetStatus.ACCEPTED else '0',
        })

    items.sort(key=lambda x: x['placed_at'], reverse=True)
    return JsonResponse({'bets': items})


@login_required
@transaction.atomic
def cashout_combined_bet(request, bet_id):
    """Cash-out de una combinada aceptada."""
    bet = get_object_or_404(
        CombinedBet,
        id=bet_id,
        user=request.user,
    )
    if bet.status != BetStatus.ACCEPTED:
        return JsonResponse({'success': False, 'error': 'Solo puedes hacer cash-out de combinadas aceptadas.'})

    cashout_amount = bet.calculated_cashout
    if cashout_amount <= Decimal('0'):
        return JsonResponse({'success': False, 'error': 'Cash-out no disponible para esta combinada.'})

    try:
        bet.cash_out(cashout_amount)
        bet.settle()
        bet.save()
        return JsonResponse({
            'success': True,
            'bet_id': bet.bet_id,
            'cashout_amount': str(cashout_amount),
            'message': f'Cash-out exitoso: {cashout_amount} fichas acreditadas.',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

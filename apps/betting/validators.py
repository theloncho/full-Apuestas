from django.utils import timezone
from decimal import Decimal

MIN_STAKE = Decimal('1.0000')
MAX_STAKE = Decimal('1000.0000')


def validate_bet_placement(user, selection, stake: Decimal, market):
    """Valida que una apuesta pueda ser colocada."""
    errors = []

    if not user.is_active_for_betting:
        errors.append("Tu cuenta no está habilitada para apostar.")

    event = selection.market.event
    from apps.betting.models import EventStatus
    if event.status == EventStatus.FINISHED:
        errors.append("El evento ya ha finalizado y no acepta más apuestas.")
    elif event.scheduled_at <= timezone.now() and event.status != EventStatus.LIVE:
        errors.append("El evento ya comenzó y no acepta apuestas pre-partido.")

    if market.is_suspended:
        if market.suspended_until and timezone.now() < market.suspended_until:
            errors.append("Este mercado está suspendido temporalmente.")
        elif market.is_suspended:
            errors.append("Este mercado está suspendido.")

    if stake < MIN_STAKE:
        errors.append(f"Apuesta mínima: {MIN_STAKE} fichas.")

    if stake > MAX_STAKE:
        errors.append(f"Apuesta máxima: {MAX_STAKE} fichas.")

    from apps.wallet.models import WalletService
    balance = WalletService.get_balance(user)
    if balance < stake:
        errors.append(f"Saldo insuficiente. Disponible: {balance:.2f} fichas.")

    return errors


def validate_combined_bet_selections(selections):
    """Detectar selecciones mutuamente excluyentes del mismo evento (contingencias relacionadas)."""
    event_market_pairs = [(sel.market.event_id, sel.market_id) for sel in selections]
    if len(event_market_pairs) != len(set(event_market_pairs)):
        raise ValueError(
            "No puedes combinar múltiples selecciones del mismo mercado en el mismo evento."
        )


def validate_combined_bet_placement(user, selections, stake: Decimal):
    """Valida que una combinada pueda ser colocada."""
    from apps.betting.models import EventStatus, Market

    errors = []
    if not user.is_active_for_betting:
        errors.append("Tu cuenta no está habilitada para apostar.")
    if len(selections) < 2:
        errors.append("Se necesitan al menos 2 selecciones para una combinada.")

    if stake < MIN_STAKE:
        errors.append(f"Apuesta mínima: {MIN_STAKE} fichas.")
    if stake > MAX_STAKE:
        errors.append(f"Apuesta máxima: {MAX_STAKE} fichas.")

    from apps.wallet.models import WalletService
    balance = WalletService.get_balance(user)
    if balance < stake:
        errors.append(f"Saldo insuficiente. Disponible: {balance:.2f} fichas.")

    # Validar cada selección
    for sel in selections:
        event = sel.market.event
        if event.status == EventStatus.FINISHED:
            errors.append(f"'{sel.name}' — El evento ya finalizó.")
            continue
        if event.scheduled_at <= timezone.now() and event.status != EventStatus.LIVE:
            errors.append(f"'{sel.name}' — El evento ya comenzó.")
            continue

        market = Market.objects.get(id=sel.market_id)
        if market.is_suspended:
            errors.append(f"'{sel.name}' — Mercado suspendido.")

    # Mutuamente excluyentes
    try:
        validate_combined_bet_selections(selections)
    except ValueError as e:
        errors.append(str(e))

    return errors

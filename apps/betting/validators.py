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
    """Detectar selecciones mutuamente excluyentes del mismo mercado."""
    market_ids = [sel.market_id for sel in selections]
    if len(market_ids) != len(set(market_ids)):
        raise ValueError(
            "No puedes combinar selecciones del mismo mercado "
            "(son mutuamente excluyentes)."
        )

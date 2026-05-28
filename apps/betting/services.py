from decimal import Decimal
from django.db import transaction
from .models import Bet, BetStatus, Event, EventStatus, Selection, CombinedBet


class LiquidationService:
    """
    Liquida todas las apuestas de un evento cuando se marca resultado.
    Operación atómica: todas las apuestas se resuelven o ninguna.
    """

    @classmethod
    @transaction.atomic
    def liquidate_event(cls, event: Event, result_home: int, result_away: int):
        """Resuelve el evento y liquida todas las apuestas asociadas."""
        event.result_home = result_home
        event.result_away = result_away
        event.status = EventStatus.FINISHED
        event.save()

        # Resolver selecciones según tipo de mercado
        cls._resolve_1x2_selections(event, result_home, result_away)
        cls._resolve_over_under_selections(event, result_home, result_away)
        cls._resolve_btts_selections(event, result_home, result_away)
        cls._resolve_asian_handicap_selections(event, result_home, result_away)

        # Liquidar apuestas simples aceptadas
        bets = Bet.objects.select_for_update().filter(
            selection__market__event=event,
            status=BetStatus.ACCEPTED,
        )
        for bet in bets:
            bet.start_settling()
            bet.save()
            if bet.selection.is_winner:
                bet.mark_won()
            else:
                bet.mark_lost()
            bet.settle()
            bet.save()

        # Liquidar combinadas que incluyan selecciones de este evento
        cls._settle_combined_bets_for_event(event)

        from apps.audit.models import AuditLog
        AuditLog.log('event_liquidated', {
            'event_id': event.id,
            'result': f'{result_home}-{result_away}',
            'bets_settled': bets.count(),
        })

    @classmethod
    def _settle_combined_bets_for_event(cls, event: Event):
        """Resuelve combinadas que contienen selecciones del evento liquidado."""
        affected_ids = CombinedBet.objects.filter(
            selections__market__event=event,
            status=BetStatus.ACCEPTED,
        ).values_list('id', flat=True).distinct()

        for cb_id in affected_ids:
            cb = CombinedBet.objects.select_for_update().get(id=cb_id)
            cb.start_settling()
            cb.save()

            # Verificar todas las selecciones de la combinada
            all_won = all(
                sel.is_winner is True
                for sel in cb.selections.all()
            )
            any_lost = any(
                sel.is_winner is False
                for sel in cb.selections.all()
            )
            any_pending = any(
                sel.is_winner is None
                for sel in cb.selections.all()
            )

            if any_pending:
                # No todas las selecciones están resueltas aún — volver a ACCEPTED
                cb.status = BetStatus.ACCEPTED
                cb.save()
                continue

            if all_won:
                cb.mark_won()
            elif any_lost:
                cb.mark_lost()
            cb.settle()
            cb.save()

    @classmethod
    @transaction.atomic
    def cancel_event(cls, event: Event):
        """Anula un evento: devuelve stake de todas las apuestas."""
        event.status = EventStatus.CANCELLED
        event.save()

        bets = Bet.objects.select_for_update().filter(
            selection__market__event=event,
            status=BetStatus.ACCEPTED,
        )
        for bet in bets:
            bet.void_bet()
            bet.settle()
            bet.save()

    @staticmethod
    def _resolve_1x2_selections(event, result_home, result_away):
        for market in event.markets.filter(market_type='1X2'):
            for sel in market.selections.all():
                if sel.name == '1':
                    sel.is_winner = result_home > result_away
                elif sel.name == 'X':
                    sel.is_winner = result_home == result_away
                elif sel.name == '2':
                    sel.is_winner = result_away > result_home
                sel.save()

    @staticmethod
    def _resolve_over_under_selections(event, result_home, result_away):
        total_goals = result_home + result_away
        for market in event.markets.filter(market_type='over_under'):
            line = market.line or Decimal('2.5')
            for sel in market.selections.all():
                if 'Over' in sel.name:
                    sel.is_winner = total_goals > line
                elif 'Under' in sel.name:
                    sel.is_winner = total_goals < line
                sel.save()

    @staticmethod
    def _resolve_btts_selections(event, result_home, result_away):
        both_scored = result_home > 0 and result_away > 0
        for market in event.markets.filter(market_type='btts'):
            for sel in market.selections.all():
                if sel.name == 'Sí':
                    sel.is_winner = both_scored
                elif sel.name == 'No':
                    sel.is_winner = not both_scored
                sel.save()

    @staticmethod
    def _resolve_asian_handicap_selections(event, result_home, result_away):
        for market in event.markets.filter(market_type='handicap_asiatico'):
            for sel in market.selections.all():
                try:
                    # sel.name is expected to be "1 +1.5" or "2 -1.5"
                    team, point_str = sel.name.rsplit(' ', 1)
                    point = Decimal(point_str)
                    
                    if team == '1':
                        adjusted_home = Decimal(result_home) + point
                        sel.is_winner = adjusted_home > Decimal(result_away)
                    elif team == '2':
                        adjusted_away = Decimal(result_away) + point
                        sel.is_winner = Decimal(result_home) < adjusted_away
                    else:
                        sel.is_winner = False # Fallback si el nombre está mal formateado
                except Exception:
                    sel.is_winner = False
                sel.save()


class OddsService:
    """Calcula cuotas con margen del operador."""

    @staticmethod
    def calculate_fair_odds(probability: Decimal) -> Decimal:
        """Cuota justa = 1 / probabilidad."""
        if probability <= Decimal('0') or probability >= Decimal('1'):
            raise ValueError("Probabilidad debe estar entre 0 y 1 exclusivo.")
        return (Decimal('1') / probability).quantize(Decimal('0.0001'))

    @staticmethod
    def apply_margin(fair_odds: Decimal, margin: Decimal = Decimal('0.05')) -> Decimal:
        """Cuota con margen = cuota_justa × (1 − margen)."""
        return (fair_odds * (Decimal('1') - margin)).quantize(Decimal('0.0001'))

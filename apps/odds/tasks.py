import logging
from decimal import Decimal

from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

logger = logging.getLogger(__name__)


@shared_task
def broadcast_odds_update(event_id: int, market_data: dict, requires_reconfirmation: bool = False):
    """Envía actualización de odds a todos los clientes suscritos al evento."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'odds_{event_id}',
        {
            'type': 'odds_update',
            'data': market_data,
            'requires_reconfirmation': requires_reconfirmation,
        }
    )


@shared_task
def suspend_market_temporarily(market_id: int, seconds: int = 30):
    """
    Suspende un mercado N segundos por evento crítico (gol, expulsión).
    Al expirar, reactiva automáticamente.
    """
    from apps.betting.models import Market
    try:
        market = Market.objects.get(id=market_id)
        market.is_suspended = True
        market.suspended_until = timezone.now() + timedelta(seconds=seconds)
        market.save()

        # Notificar clientes
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'odds_{market.event_id}',
            {
                'type': 'market_suspended',
                'market_id': market_id,
                'suspended_until': market.suspended_until.isoformat(),
            }
        )

        # Programar reactivación
        reactivate_market.apply_async((market_id,), countdown=seconds)
    except Market.DoesNotExist:
        pass


@shared_task
def reactivate_market(market_id: int):
    """Reactiva un mercado suspendido si ya pasó el tiempo."""
    from apps.betting.models import Market
    try:
        market = Market.objects.get(id=market_id)
        if market.suspended_until and timezone.now() >= market.suspended_until:
            market.is_suspended = False
            market.suspended_until = None
            market.save()

            # Notificar reactivación
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'odds_{market.event_id}',
                {
                    'type': 'odds_update',
                    'data': {'market_reactivated': market_id},
                    'requires_reconfirmation': False,
                }
            )
    except Market.DoesNotExist:
        pass


# ─── The Odds API: sincronización automática ─────────────────────────────────


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def fetch_and_sync_odds(self):
    """
    Tarea periódica (Celery Beat) que sincroniza cuotas reales desde The Odds API.

    Flujo:
    1. Llama a la API para obtener odds de fútbol
    2. Hace match con nuestros eventos por nombre de equipo
    3. Si las cuotas cambiaron, actualiza Selection.odds
    4. Dispara broadcast_odds_update por WebSocket
    5. Registra cada cambio en AuditLog

    Si la API falla o la quota se agota, simplemente loguea y no rompe nada.
    """
    from apps.betting.models import Event, EventStatus, Selection
    from apps.audit.models import AuditLog

    try:
        from apps.odds.odds_api_client import OddsAPIClient, OddsAPIError, QuotaExhaustedError
        client = OddsAPIClient()
    except OddsAPIError as e:
        logger.warning('odds_sync_skip', extra={'reason': str(e)})
        return {'status': 'skipped', 'reason': str(e)}

    try:
        api_events = client.fetch_odds()
    except QuotaExhaustedError as e:
        logger.warning('odds_quota_exhausted', extra={'detail': str(e)})
        return {'status': 'quota_exhausted', 'detail': str(e)}
    except OddsAPIError as e:
        logger.error('odds_api_error', extra={'detail': str(e)})
        # Reintentar con backoff
        raise self.retry(exc=e)

    if not api_events:
        logger.info('odds_sync_no_events')
        return {'status': 'no_events', 'synced': 0}

    # Obtener nuestros eventos activos
    our_events = Event.objects.filter(
        status__in=[EventStatus.SCHEDULED, EventStatus.LIVE],
    ).prefetch_related('markets__selections')

    # Construir un índice para match por nombre de equipo (case-insensitive)
    event_index = {}
    for ev in our_events:
        key = _normalize_match_key(ev.home_team, ev.away_team)
        event_index[key] = ev

    synced_count = 0
    created_count = 0
    changes = []

    # Obtener o crear el deporte Fútbol
    from apps.betting.models import Sport, Market, MarketType
    football, _ = Sport.objects.get_or_create(
        slug='futbol', defaults={'name': 'Fútbol', 'icon': 'bi-trophy'}
    )

    for api_event in api_events:
        home = api_event.get('home_team', '')
        away = api_event.get('away_team', '')
        match_key = _normalize_match_key(home, away)
        commence = api_event.get('commence_time', '')

        our_event = event_index.get(match_key)

        # ─── Si no existe, CREAR el evento con cuotas reales ──────────
        if not our_event:
            from django.utils.dateparse import parse_datetime
            scheduled = parse_datetime(commence) if commence else timezone.now()

            # Determinar estado
            is_live = scheduled and scheduled <= timezone.now()
            status = EventStatus.LIVE if is_live else EventStatus.SCHEDULED

            our_event, was_created = Event.objects.get_or_create(
                home_team=home,
                away_team=away,
                defaults={
                    'sport': football,
                    'scheduled_at': scheduled,
                    'status': status,
                },
            )
            if was_created:
                created_count += 1
                # Crear mercados con cuotas de la API
                h2h_odds = OddsAPIClient.extract_best_odds(api_event, 'h2h')
                totals_odds = OddsAPIClient.extract_best_odds(api_event, 'totals')
                spreads_odds = OddsAPIClient.extract_best_odds(api_event, 'spreads')

                _create_markets_from_api(our_event, h2h_odds, totals_odds, spreads_odds, home, away)

                event_index[match_key] = our_event
                logger.info('event_imported', extra={
                    'home': home, 'away': away, 'odds': str(h2h_odds),
                })
                continue  # Ya creamos con cuotas correctas, no hace falta actualizar

        # Extraer las mejores odds (promedio de casas)
        h2h_odds = OddsAPIClient.extract_best_odds(api_event, 'h2h')
        totals_odds = OddsAPIClient.extract_best_odds(api_event, 'totals')
        spreads_odds = OddsAPIClient.extract_best_odds(api_event, 'spreads')

        with transaction.atomic():
            for market in our_event.markets.all():
                for selection in market.selections.all():
                    new_odds = _find_new_odds(
                        selection, market, h2h_odds, totals_odds, spreads_odds,
                        home, away,
                    )
                    if new_odds and new_odds != selection.odds:
                        old_odds = selection.odds
                        selection.odds = new_odds
                        selection.save(update_fields=['odds', 'updated_at'])

                        changes.append({
                            'event': str(our_event),
                            'selection': selection.name,
                            'old': str(old_odds),
                            'new': str(new_odds),
                        })

            if changes:
                synced_count += 1
                # Broadcast por WebSocket
                broadcast_odds_update.delay(
                    our_event.id,
                    {
                        'event_id': our_event.id,
                        'source': 'the_odds_api',
                        'changes': changes[-len(our_event.markets.all()):],
                    },
                    requires_reconfirmation=True,
                )

    # Auditoría global
    if changes:
        try:
            AuditLog.log(
                'odds_synced_from_api',
                {
                    'source': 'the_odds_api',
                    'events_synced': synced_count,
                    'total_changes': len(changes),
                    'details': changes[:20],  # limitar para no desbordar el log
                },
            )
        except Exception:
            pass  # No fallar por auditoría

    result = {
        'status': 'success',
        'events_matched': synced_count,
        'events_created': created_count,
        'odds_changed': len(changes),
    }
    logger.info('odds_sync_complete', extra=result)
    return result


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def sync_live_scores(self):
    """
    Sincroniza marcadores en vivo desde The Odds API.
    Solo se ejecuta si hay eventos en estado 'en_vivo'.
    """
    from apps.betting.models import Event, EventStatus
    from django.utils import timezone

    # Auto-transición a EN VIVO para partidos que ya comenzaron
    now = timezone.now()
    Event.objects.filter(
        status=EventStatus.SCHEDULED,
        scheduled_at__lte=now
    ).update(status=EventStatus.LIVE)

    # Auto-transición a FINALIZADO por seguridad si pasaron > 150 mins (2.5 horas)
    from datetime import timedelta
    finished_threshold = now - timedelta(minutes=150)
    Event.objects.filter(
        status=EventStatus.LIVE,
        scheduled_at__lte=finished_threshold
    ).update(status=EventStatus.FINISHED)

    # Solo ejecutar si hay eventos en vivo
    live_count = Event.objects.filter(status=EventStatus.LIVE).count()
    if live_count == 0:
        return {'status': 'skipped', 'reason': 'no_live_events'}

    try:
        from apps.odds.odds_api_client import OddsAPIClient, OddsAPIError
        client = OddsAPIClient()
        scores = client.fetch_scores()
    except OddsAPIError as e:
        logger.warning('scores_api_error', extra={'detail': str(e)})
        return {'status': 'error', 'reason': str(e)}

    if not scores:
        return {'status': 'no_scores'}

    updated = 0
    for score_event in scores:
        if not score_event.get('scores'):
            continue

        home = score_event.get('home_team', '')
        away = score_event.get('away_team', '')

        try:
            # Buscar el partido más reciente de estos equipos
            event = Event.objects.filter(
                home_team__iexact=home.strip(),
                away_team__iexact=away.strip(),
                status__in=[EventStatus.LIVE, EventStatus.FINISHED],
            ).order_by('-scheduled_at').first()
            if not event:
                continue
        except Exception:
            continue

        # Actualizar marcador
        goal_detected = False
        for s in score_event['scores']:
            name = s.get('name', '').lower().strip()
            raw_score = s.get('score')
            
            # Robust parsing of the score
            try:
                if raw_score is None or raw_score == '':
                    score_int = 0
                else:
                    score_int = int(raw_score)
            except (ValueError, TypeError):
                score_int = 0

            if name == home.lower().strip():
                if event.result_home is not None and score_int > event.result_home:
                    goal_detected = True
                event.result_home = score_int
            elif name == away.lower().strip():
                if event.result_away is not None and score_int > event.result_away:
                    goal_detected = True
                event.result_away = score_int

        # Verificar si finalizó según la API
        event_completed = False
        if score_event.get('completed', False):
            event.status = EventStatus.FINISHED
            event_completed = True

        event.save(update_fields=['result_home', 'result_away', 'status'])
        updated += 1
        
        # Suspend if goal detected
        if goal_detected:
            for market in event.markets.all():
                suspend_market_temporarily.delay(market.id, seconds=30)

        # Broadcast score update
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'odds_{event.id}',
            {
                'type': 'odds_update',
                'data': {
                    'event_id': event.id,
                    'score_home': event.result_home,
                    'score_away': event.result_away,
                    'source': 'the_odds_api_scores',
                    'completed': event_completed,
                },
                'requires_reconfirmation': False,
            }
        )
        
        # Auto-liquidation
        if event_completed:
            try:
                from apps.betting.services import LiquidationService
                LiquidationService.liquidate_event(event, event.result_home, event.result_away)
                logger.info('auto_liquidation_success', extra={'event_id': event.id})
            except Exception as e:
                logger.error('auto_liquidation_failed', extra={'event_id': event.id, 'error': str(e)})

    return {'status': 'success', 'scores_updated': updated}


# ─── Helpers internos ─────────────────────────────────────────────────────────


def _normalize_match_key(home: str, away: str) -> str:
    """Normaliza nombres de equipo para matching fuzzy."""
    return f"{home.lower().strip()}|{away.lower().strip()}"


def _find_new_odds(
    selection, market, h2h_odds: dict, totals_odds: dict, spreads_odds: dict,
    api_home: str, api_away: str,
) -> Decimal | None:
    """
    Busca la cuota actualizada para una selección dada,
    mapeando entre los nombres de la API y nuestros nombres internos.
    """
    from apps.odds.odds_api_client import OddsAPIClient

    if market.market_type == '1X2':
        # Mapear cada outcome de h2h a nuestro '1', 'X', '2'
        for outcome_name, odds_value in h2h_odds.items():
            mapped = OddsAPIClient.map_outcome_to_selection(
                outcome_name, api_home, api_away,
            )
            if mapped == selection.name:
                return odds_value

    elif market.market_type == 'over_under':
        for outcome_name, odds_value in totals_odds.items():
            mapped = OddsAPIClient.map_outcome_to_selection(
                outcome_name, api_home, api_away,
            )
            if mapped and mapped.lower().startswith(selection.name.lower()[:4]):
                return odds_value

    elif market.market_type == 'handicap_asiatico':
        for outcome_name, odds_value in spreads_odds.items():
            mapped = OddsAPIClient.map_outcome_to_selection(
                outcome_name, api_home, api_away,
            )
            if mapped == selection.name:
                return odds_value

    return None


def _create_markets_from_api(
    event, h2h_odds: dict, totals_odds: dict, spreads_odds: dict,
    api_home: str, api_away: str,
):
    """
    Crea mercados y selecciones para un evento nuevo
    usando cuotas reales de la API.
    """
    from apps.betting.models import Market, MarketType, Selection
    from apps.odds.odds_api_client import OddsAPIClient

    # ─── Mercado 1X2 ──────────────────────────────────────────────────
    if h2h_odds:
        market_1x2, _ = Market.objects.get_or_create(
            event=event, market_type=MarketType.HOME_DRAW_AWAY,
        )
        for outcome_name, odds_value in h2h_odds.items():
            mapped = OddsAPIClient.map_outcome_to_selection(
                outcome_name, api_home, api_away,
            )
            if mapped in ('1', 'X', '2'):
                Selection.objects.update_or_create(
                    market=market_1x2, name=mapped,
                    defaults={'odds': odds_value},
                )

    # ─── Mercado Over/Under ───────────────────────────────────────────
    if totals_odds:
        from decimal import Decimal
        ou_market, _ = Market.objects.get_or_create(
            event=event,
            market_type=MarketType.OVER_UNDER,
            defaults={'line': Decimal('2.5')},
        )
        for outcome_name, odds_value in totals_odds.items():
            sel_name = outcome_name.strip()
            if 'over' in sel_name.lower():
                sel_name = 'Over 2.5'
            elif 'under' in sel_name.lower():
                sel_name = 'Under 2.5'
            Selection.objects.update_or_create(
                market=ou_market, name=sel_name,
                defaults={'odds': odds_value},
            )

    # ─── Mercado Handicap Asiático ────────────────────────────────────
    if spreads_odds:
        ah_market, _ = Market.objects.get_or_create(
            event=event,
            market_type=MarketType.ASIAN_HANDICAP,
        )
        for outcome_name, odds_value in spreads_odds.items():
            mapped = OddsAPIClient.map_outcome_to_selection(outcome_name, api_home, api_away)
            if mapped:
                Selection.objects.update_or_create(
                    market=ah_market, name=mapped,
                    defaults={'odds': odds_value},
                )


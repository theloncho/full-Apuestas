from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import serializers, status
from decimal import Decimal

from .models import Event, Selection, Bet, BetStatus
from .services import LiquidationService


class EventSerializer(serializers.ModelSerializer):
    sport_name = serializers.CharField(source='sport.name', read_only=True)

    class Meta:
        model = Event
        fields = ['id', 'sport_name', 'home_team', 'away_team', 'scheduled_at',
                  'status', 'result_home', 'result_away']


class SelectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Selection
        fields = ['id', 'name', 'odds', 'is_winner']


class BetSerializer(serializers.ModelSerializer):
    selection_name = serializers.CharField(source='selection.name', read_only=True)
    event = serializers.CharField(source='selection.market.event', read_only=True)

    class Meta:
        model = Bet
        fields = ['id', 'selection_name', 'event', 'stake', 'odds_at_placement',
                  'status', 'payout', 'cashout_amount', 'placed_at', 'settled_at']


@api_view(['GET'])
def api_events(request):
    events = Event.objects.filter(
        status__in=['programado', 'en_vivo']
    ).select_related('sport')
    return Response(EventSerializer(events, many=True).data)


@api_view(['GET'])
def api_event_odds(request, event_id):
    try:
        event = Event.objects.prefetch_related('markets__selections').get(id=event_id)
    except Event.DoesNotExist:
        return Response({'error': 'Evento no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    markets = []
    for market in event.markets.all():
        markets.append({
            'market_id': market.id,
            'market_type': market.market_type,
            'is_suspended': market.is_suspended,
            'line': str(market.line) if market.line else None,
            'selections': SelectionSerializer(market.selections.all(), many=True).data,
        })
    return Response({'event': EventSerializer(event).data, 'markets': markets})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_my_bets(request):
    bets = Bet.objects.filter(user=request.user).select_related(
        'selection__market__event'
    ).order_by('-placed_at')[:50]
    return Response(BetSerializer(bets, many=True).data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def api_liquidate_event(request, event_id):
    """Admin: liquidar un evento con resultado."""
    try:
        event = Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        return Response({'error': 'Evento no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    result_home = request.data.get('result_home')
    result_away = request.data.get('result_away')
    if result_home is None or result_away is None:
        return Response({'error': 'Debes enviar result_home y result_away'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        LiquidationService.liquidate_event(event, int(result_home), int(result_away))
        return Response({'status': 'liquidated', 'result': f'{result_home}-{result_away}'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


app_name = 'betting-api'

urlpatterns = [
    path('events/', api_events, name='events'),
    path('events/<int:event_id>/odds/', api_event_odds, name='event_odds'),
    path('events/<int:event_id>/liquidate/', api_liquidate_event, name='liquidate_event'),
    path('bets/', api_my_bets, name='my_bets'),
]

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from apps.betting.models import Event


class OddsConsumer(AsyncWebsocketConsumer):
    """
    Canal WebSocket por evento.
    El cliente se suscribe a un evento y recibe actualizaciones
    de odds en tiempo real cuando cambian.
    """

    async def connect(self):
        self.event_id = self.scope['url_route']['kwargs']['event_id']
        self.group_name = f'odds_{self.event_id}'

        # Unirse al grupo del evento
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Enviar odds actuales al conectar
        odds = await self.get_current_odds(self.event_id)
        await self.send(text_data=json.dumps({
            'type': 'odds_update',
            'data': odds,
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """El cliente puede enviar 'ping' para forzar refresh."""
        try:
            data = json.loads(text_data)
            if data.get('type') == 'ping':
                odds = await self.get_current_odds(self.event_id)
                await self.send(text_data=json.dumps({
                    'type': 'odds_update',
                    'data': odds,
                }))
        except json.JSONDecodeError:
            pass

    async def odds_update(self, event):
        """Recibe mensajes del channel layer y los reenvía al WebSocket."""
        await self.send(text_data=json.dumps({
            'type': 'odds_update',
            'data': event['data'],
            'requires_reconfirmation': event.get('requires_reconfirmation', False),
        }))

    async def market_suspended(self, event):
        """Notifica al cliente que un mercado fue suspendido."""
        await self.send(text_data=json.dumps({
            'type': 'market_suspended',
            'market_id': event['market_id'],
            'suspended_until': event['suspended_until'],
        }))

    @database_sync_to_async
    def get_current_odds(self, event_id):
        """Obtiene las cuotas actuales de un evento."""
        try:
            event = Event.objects.get(id=event_id)
            result = {
                'event_id': int(event_id),
                'status': event.status,
                'markets': [],
            }
            for market in event.markets.prefetch_related('selections').all():
                result['markets'].append({
                    'market_id': market.id,
                    'market_type': market.market_type,
                    'is_suspended': market.is_suspended,
                    'selections': [
                        {
                            'selection_id': sel.id,
                            'name': sel.name,
                            'odds': str(sel.odds),
                        }
                        for sel in market.selections.all()
                    ],
                })
            return result
        except Event.DoesNotExist:
            return {}

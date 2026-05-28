import json
from channels.generic.websocket import AsyncWebsocketConsumer

class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Solo personal autorizado debería poder conectarse,
        # pero en Django Channels self.scope['user'] tiene esa info
        # si se usa AuthMiddlewareStack.
        if self.scope["user"].is_anonymous or not self.scope["user"].is_staff:
            await self.close()
            return

        self.group_name = "dashboard_group"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def dashboard_update(self, event):
        # Recibir mensaje de la capa de canales
        print(f"WS Consumer received event: {event}")
        message = event['message']

        # Enviar mensaje al WebSocket
        await self.send(text_data=json.dumps(message))

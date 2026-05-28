import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

django_asgi_app = get_asgi_application()

# Importar después de django.setup()
from apps.odds.routing import websocket_urlpatterns as odds_urls  # noqa: E402
from apps.dashboard.routing import websocket_urlpatterns as dash_urls  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            odds_urls + dash_urls
        )
    ),
})

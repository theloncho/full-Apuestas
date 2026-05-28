from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/odds/(?P<event_id>\d+)/$', consumers.OddsConsumer.as_asgi()),
]

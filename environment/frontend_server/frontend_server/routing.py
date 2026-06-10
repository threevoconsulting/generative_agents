"""
Channels ASGI routing for the frontend server.

Only the WebSocket protocol is declared here; HTTP continues to be served by
Django's normal view system (Channels 2.x falls back to it automatically). This
file is only imported when `channels` is installed (see settings.base).
"""
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import re_path

from translator.consumers import SimConsumer

application = ProtocolTypeRouter({
    "websocket": URLRouter([
        re_path(r"^ws/sim/$", SimConsumer),
    ]),
})

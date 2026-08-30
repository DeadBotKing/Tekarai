"""ASGI entrypoint — Django + Channels protocol routing (Phase 08 §8/§30).

``daphne`` sits at the top of INSTALLED_APPS so ``runserver`` serves ASGI
directly; REST keeps working through the same application object.
"""

from __future__ import annotations

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

djangoAsgiApp = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402 — after app setup

from apps.communication.presentation.ws.routing import websocketUrlPatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": djangoAsgiApp,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocketUrlPatterns))
        ),
    }
)

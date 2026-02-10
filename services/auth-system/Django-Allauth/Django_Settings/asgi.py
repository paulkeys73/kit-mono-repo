#E:\auth-system\Django-Allauth\Django_Settings\asgi.py



import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
import auth_app.router.ws_routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Django_Settings.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            auth_app.router.ws_routing.websocket_urlpatterns
        )
    ),
})


#E:\auth-system\Django-Allauth\auth_app\router\ws_routing.py





from django.urls import re_path
from auth_app.workers import auth_worker

websocket_urlpatterns = [
    re_path(r"ws/auth/(?P<user_id>\d+)/$", auth_worker.EventConsumer.as_asgi())

]


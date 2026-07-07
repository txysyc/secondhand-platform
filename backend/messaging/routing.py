from django.urls import path

from messaging.consumers import PrivateMessageConsumer

websocket_urlpatterns = [
    path("ws/messages/<int:conversation_id>/", PrivateMessageConsumer.as_asgi()),
]

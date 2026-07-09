"""messaging 应用 pytest 测试。"""

from decimal import Decimal
from uuid import uuid4

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from catalog.models import Category, Listing
from catalog.selectors import (
    _active_category_ids_cache_key,
    get_active_category_ids,
)
from messaging.admin import ConversationAdmin, PrivateMessageAdmin
from messaging.auth import JwtAuthMiddlewareStack
from messaging.models import Conversation, PrivateMessage
from messaging.routing import websocket_urlpatterns
from messaging.selectors import (
    _latest_message_window_cache_key,
    get_conversation_for_user,
    get_conversation_message_window,
    get_user_conversations,
)
from messaging.services import (
    create_private_message,
    get_or_create_conversation,
    mark_conversation_read,
)


pytestmark = pytest.mark.django_db
User = get_user_model()

@pytest.fixture
def websocket_settings(settings):
    """使用内存 channel layer 隔离 WebSocket 测试。"""

    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }


@database_sync_to_async
def _create_async_users(prefix):
    """在线程池中创建 WebSocket 测试用户。"""

    suffix = uuid4().hex[:4]
    return {
        "buyer": User.objects.create_user(
            username=f"{prefix}买{suffix}",
            email=f"{prefix}-buyer-{suffix}@example.com",
            password="StrongPass123",
        ),
        "seller": User.objects.create_user(
            username=f"{prefix}卖{suffix}",
            email=f"{prefix}-seller-{suffix}@example.com",
            password="StrongPass123",
        ),
        "other": User.objects.create_user(
            username=f"{prefix}路{suffix}",
            email=f"{prefix}-other-{suffix}@example.com",
            password="StrongPass123",
        ),
    }


@database_sync_to_async
def _get_or_create_conversation_for_async(buyer, seller):
    return get_or_create_conversation(buyer, seller)


@database_sync_to_async
def _private_message_count(content):
    return PrivateMessage.objects.filter(content=content).count()


@database_sync_to_async
def _access_token_for(user):
    return str(AccessToken.for_user(user))


@database_sync_to_async
def _refresh_token_for(user):
    return str(RefreshToken.for_user(user))


@pytest.mark.django_db(transaction=True)
class TestPrivateMessageConsumer:
    """私信 WebSocket Consumer 测试。"""

    async def test_participant_can_send_message_over_websocket(self, websocket_settings):
        users = await _create_async_users("异步")
        conversation = await _get_or_create_conversation_for_async(
            users["buyer"],
            users["seller"],
        )
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/messages/{conversation.pk}/",
        )
        communicator.scope["user"] = users["buyer"]

        connected, _ = await communicator.connect()
        assert connected is True

        await communicator.send_json_to({"content": "WebSocket 私信"})
        response = await communicator.receive_json_from()

        assert response["type"] == "message"
        assert response["message"]["content"] == "WebSocket 私信"
        assert await _private_message_count("WebSocket 私信") == 1
        await communicator.disconnect()

    async def test_non_participant_connection_is_rejected(self, websocket_settings):
        users = await _create_async_users("异步")
        conversation = await _get_or_create_conversation_for_async(
            users["buyer"],
            users["seller"],
        )
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/messages/{conversation.pk}/",
        )
        communicator.scope["user"] = users["other"]

        connected, _ = await communicator.connect()

        assert connected is False


@pytest.mark.django_db(transaction=True)
class TestPrivateMessageJwtConsumer:
    """私信 WebSocket JWT 鉴权测试。"""

    async def test_participant_can_connect_and_send_with_access_token(
        self,
        websocket_settings,
    ):
        users = await _create_async_users("ws")
        conversation = await _get_or_create_conversation_for_async(
            users["buyer"],
            users["seller"],
        )
        token = await _access_token_for(users["buyer"])
        communicator = WebsocketCommunicator(
            JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
            f"/ws/messages/{conversation.pk}/?token={token}",
        )

        connected, _ = await communicator.connect()
        assert connected is True

        await communicator.send_json_to({"content": "JWT WebSocket 私信"})
        response = await communicator.receive_json_from()

        assert response["type"] == "message"
        assert response["message"]["content"] == "JWT WebSocket 私信"
        assert response["message"]["sender"]["id"] == users["buyer"].id
        assert await _private_message_count("JWT WebSocket 私信") == 1
        await communicator.disconnect()

    async def test_missing_invalid_or_non_participant_token_is_rejected(
        self,
        websocket_settings,
    ):
        users = await _create_async_users("ws")
        conversation = await _get_or_create_conversation_for_async(
            users["buyer"],
            users["seller"],
        )
        other_token = await _access_token_for(users["other"])

        for path in [
            f"/ws/messages/{conversation.pk}/",
            f"/ws/messages/{conversation.pk}/?token=invalid-token",
            f"/ws/messages/{conversation.pk}/?token={other_token}",
        ]:
            communicator = WebsocketCommunicator(
                JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
                path,
            )
            connected, _ = await communicator.connect()
            assert connected is False
            await communicator.disconnect()

    async def test_refresh_token_is_rejected_for_websocket(self, websocket_settings):
        users = await _create_async_users("ws")
        conversation = await _get_or_create_conversation_for_async(
            users["buyer"],
            users["seller"],
        )
        refresh = await _refresh_token_for(users["buyer"])
        communicator = WebsocketCommunicator(
            JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
            f"/ws/messages/{conversation.pk}/?token={refresh}",
        )

        connected, _ = await communicator.connect()

        assert connected is False
        await communicator.disconnect()

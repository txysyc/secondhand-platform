from uuid import uuid4

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from messaging.models import Conversation, PrivateMessage
from messaging.auth import JwtAuthMiddlewareStack
from messaging.routing import websocket_urlpatterns
from messaging.services import (
    create_private_message,
    get_or_create_conversation,
)


User = get_user_model()


class MessagingApiTests(APITestCase):
    """P6 私信 HTTP API 测试。"""

    def setUp(self):
        self.client = APIClient()
        self.buyer = User.objects.create_user(
            username="msgbuyer",
            email="msgbuyer@example.com",
            password="StrongPass123",
        )
        self.seller = User.objects.create_user(
            username="msgseller",
            email="msgseller@example.com",
            password="StrongPass123",
        )
        self.other = User.objects.create_user(
            username="msgother",
            email="msgother@example.com",
            password="StrongPass123",
        )

    def auth_headers(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_conversation_list_requires_login(self):
        response = self.client.get(reverse("api:messaging_conversations"))

        self.assertEqual(response.status_code, 401)

    def test_start_conversation_creates_or_reuses_pair(self):
        first_response = self.client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": self.seller.id},
            format="json",
            **self.auth_headers(self.buyer),
        )
        second_response = self.client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": self.seller.id},
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(first_response.json()["id"], second_response.json()["id"])
        self.assertEqual(Conversation.objects.count(), 1)

    def test_start_conversation_rejects_self_and_inactive_target(self):
        inactive = User.objects.create_user(
            username="inactive",
            email="inactive-msg@example.com",
            password="StrongPass123",
            is_active=False,
        )

        self_response = self.client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": self.buyer.id},
            format="json",
            **self.auth_headers(self.buyer),
        )
        inactive_response = self.client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": inactive.id},
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(self_response.status_code, 400)
        self.assertEqual(self_response.json()["message"], "不能给自己发送私信")
        self.assertEqual(inactive_response.status_code, 400)

    def test_conversation_list_includes_unread_and_latest_message(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        create_private_message(self.seller, conversation, "未读 API 消息")
        other_conversation = get_or_create_conversation(self.seller, self.other)
        create_private_message(self.seller, other_conversation, "无关消息")

        response = self.client.get(
            reverse("api:messaging_conversations"),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], conversation.id)
        self.assertEqual(results[0]["unread_count"], 1)
        self.assertEqual(results[0]["latest_message_content"], "未读 API 消息")
        self.assertEqual(results[0]["other_participant"]["id"], self.seller.id)

    def test_non_participant_cannot_access_conversation_or_messages(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)

        detail_response = self.client.get(
            reverse("api:messaging_conversation_detail", kwargs={"pk": conversation.id}),
            **self.auth_headers(self.other),
        )
        messages_response = self.client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            **self.auth_headers(self.other),
        )

        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(messages_response.status_code, 403)

    def test_messages_api_lists_and_sends_with_shared_payload_shape(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        create_private_message(self.seller, conversation, "历史消息")

        list_response = self.client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            **self.auth_headers(self.buyer),
        )
        send_response = self.client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"content": "  HTTP API 私信  "},
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["results"][0]["content"], "历史消息")
        self.assertEqual(send_response.status_code, 201)
        body = send_response.json()
        self.assertEqual(body["content"], "HTTP API 私信")
        self.assertEqual(body["sender"]["id"], self.buyer.id)
        self.assertEqual(body["sender_id"], self.buyer.id)
        self.assertEqual(PrivateMessage.objects.filter(content="HTTP API 私信").count(), 1)

    def test_send_message_rejects_blank_and_overlong_content(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)

        blank_response = self.client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"content": "   "},
            format="json",
            **self.auth_headers(self.buyer),
        )
        long_response = self.client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"content": "x" * 1001},
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(blank_response.status_code, 400)
        self.assertEqual(blank_response.json()["message"], "消息内容不能为空")
        self.assertEqual(long_response.status_code, 400)

    def test_mark_conversation_read_only_updates_received_messages(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        own = create_private_message(self.buyer, conversation, "自己发出的")
        received = create_private_message(self.seller, conversation, "收到的")

        response = self.client.post(
            reverse("api:messaging_conversation_read", kwargs={"pk": conversation.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 1)
        own.refresh_from_db()
        received.refresh_from_db()
        self.assertIsNone(own.read_at)
        self.assertIsNotNone(received.read_at)


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class PrivateMessageJwtConsumerTests(TransactionTestCase):
    """P6 私信 WebSocket JWT 鉴权测试。"""

    def setUp(self):
        suffix = uuid4().hex[:4]
        self.buyer = User.objects.create_user(
            username=f"ws买{suffix}",
            email=f"ws-buyer-{suffix}@example.com",
            password="StrongPass123",
        )
        self.seller = User.objects.create_user(
            username=f"ws卖{suffix}",
            email=f"ws-seller-{suffix}@example.com",
            password="StrongPass123",
        )
        self.other = User.objects.create_user(
            username=f"ws路{suffix}",
            email=f"ws-other-{suffix}@example.com",
            password="StrongPass123",
        )

    async def test_participant_can_connect_and_send_with_access_token(self):
        conversation = await self._get_or_create_conversation()
        token = await self._access_token_for(self.buyer)
        communicator = WebsocketCommunicator(
            JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
            f"/ws/messages/{conversation.pk}/?token={token}",
        )

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await communicator.send_json_to({"content": "JWT WebSocket 私信"})
        response = await communicator.receive_json_from()

        self.assertEqual(response["type"], "message")
        self.assertEqual(response["message"]["content"], "JWT WebSocket 私信")
        self.assertEqual(response["message"]["sender"]["id"], self.buyer.id)
        count = await self._message_count("JWT WebSocket 私信")
        self.assertEqual(count, 1)
        await communicator.disconnect()

    async def test_missing_invalid_or_non_participant_token_is_rejected(self):
        conversation = await self._get_or_create_conversation()
        other_token = await self._access_token_for(self.other)

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
            self.assertFalse(connected)
            await communicator.disconnect()

    async def test_refresh_token_is_rejected_for_websocket(self):
        conversation = await self._get_or_create_conversation()
        refresh = await self._refresh_token_for(self.buyer)
        communicator = WebsocketCommunicator(
            JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
            f"/ws/messages/{conversation.pk}/?token={refresh}",
        )

        connected, _ = await communicator.connect()

        self.assertFalse(connected)
        await communicator.disconnect()

    @database_sync_to_async
    def _get_or_create_conversation(self):
        return get_or_create_conversation(self.buyer, self.seller)

    @database_sync_to_async
    def _access_token_for(self, user):
        return str(AccessToken.for_user(user))

    @database_sync_to_async
    def _refresh_token_for(self, user):
        return str(RefreshToken.for_user(user))

    @database_sync_to_async
    def _message_count(self, content):
        return PrivateMessage.objects.filter(content=content).count()

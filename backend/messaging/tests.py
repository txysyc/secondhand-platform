from decimal import Decimal
from uuid import uuid4

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient, APITestCase
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
from messaging.selectors import get_conversation_for_user, get_user_conversations
from messaging.selectors import (
    _latest_message_window_cache_key,
    get_conversation_message_window,
)
from messaging.services import (
    create_private_message,
    get_or_create_conversation,
    mark_conversation_read,
)

User = get_user_model()


class MessagingTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user(
            username="私信卖家",
            email="message-seller@example.com",
            password="StrongPass123",
        )
        cls.buyer = User.objects.create_user(
            username="私信买家",
            email="message-buyer@example.com",
            password="StrongPass123",
        )
        cls.other_user = User.objects.create_user(
            username="私信路人",
            email="message-other@example.com",
            password="StrongPass123",
        )
        cls.seller.profile.nickname = "卖家昵称"
        cls.seller.profile.save(update_fields=["nickname", "updated_at"])
        cls.category = Category.objects.create(name="私信分类")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="可私信商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
            condition=Listing.Condition.GOOD,
            description="用于私信入口测试",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
            published_at=timezone.now(),
        )


class ConversationServiceTest(MessagingTestMixin, TestCase):
    def test_get_or_create_conversation_uses_single_ordered_pair(self):
        first = get_or_create_conversation(self.buyer, self.seller)
        second = get_or_create_conversation(self.seller, self.buyer)

        self.assertEqual(first, second)
        self.assertLess(first.participant_a_id, first.participant_b_id)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_cannot_start_conversation_with_self_or_inactive_user(self):
        inactive = User.objects.create_user(
            username="停用用户",
            email="inactive-message@example.com",
            password="StrongPass123",
            is_active=False,
        )

        with self.assertRaisesMessage(ValidationError, "不能给自己发送私信"):
            get_or_create_conversation(self.buyer, self.buyer)
        with self.assertRaisesMessage(ValidationError, "目标用户不可用"):
            get_or_create_conversation(self.buyer, inactive)

    def test_create_private_message_requires_participant_and_valid_content(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)

        with self.assertRaises(PermissionDenied):
            create_private_message(self.other_user, conversation, "路人插话")
        with self.assertRaisesMessage(ValidationError, "消息内容不能为空"):
            create_private_message(self.buyer, conversation, "   ")
        with self.assertRaisesMessage(ValidationError, "消息内容不能超过 1000 个字符"):
            create_private_message(self.buyer, conversation, "x" * 1001)

        message = create_private_message(self.buyer, conversation, "请问还在吗？")

        self.assertEqual(message.sender, self.buyer)
        self.assertEqual(message.content, "请问还在吗？")

    def test_mark_conversation_read_updates_only_received_messages(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        own_message = create_private_message(self.buyer, conversation, "我发出的")
        received_message = create_private_message(self.seller, conversation, "我收到的")

        updated = mark_conversation_read(self.buyer, conversation)

        self.assertEqual(updated, 1)
        own_message.refresh_from_db()
        received_message.refresh_from_db()
        self.assertIsNone(own_message.read_at)
        self.assertIsNotNone(received_message.read_at)


class ConversationSelectorTest(MessagingTestMixin, TestCase):
    def test_get_user_conversations_returns_only_participant_conversations_with_unread_count(self):
        target = get_or_create_conversation(self.buyer, self.seller)
        create_private_message(self.seller, target, "未读消息")
        other = get_or_create_conversation(self.seller, self.other_user)
        create_private_message(self.seller, other, "无关消息")

        conversations = list(get_user_conversations(self.buyer))

        self.assertEqual(conversations, [target])
        self.assertEqual(conversations[0].unread_count, 1)
        self.assertEqual(conversations[0].latest_message_content, "未读消息")
        self.assertIsNotNone(conversations[0].latest_message_created_at)

    def test_get_conversation_for_user_rejects_non_participant(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)

        with self.assertRaises(Conversation.DoesNotExist):
            get_conversation_for_user(self.other_user, conversation.pk)


class MessagingAdminTest(MessagingTestMixin, TestCase):
    def test_messaging_models_are_registered_to_admin(self):
        self.assertIsInstance(site._registry[Conversation], ConversationAdmin)
        self.assertIsInstance(site._registry[PrivateMessage], PrivateMessageAdmin)

    def test_admin_uses_summary_instead_of_full_message_in_list_display(self):
        message_admin = site._registry[PrivateMessage]
        conversation = get_or_create_conversation(self.buyer, self.seller)
        message = create_private_message(
            self.buyer,
            conversation,
            "这是一条超过二十个字符的私信内容，用于验证摘要展示",
        )

        self.assertEqual(message_admin.short_content(message), message.content[:20])


class RedisCacheSelectorTest(TestCase):
    def setUp(self):
        cache.clear()
        Category.objects.all().delete()

    def test_active_category_ids_are_cached_and_invalidated_on_save(self):
        first = Category.objects.create(name="缓存分类一")
        ids = get_active_category_ids()
        first_cache_key = _active_category_ids_cache_key()

        self.assertEqual(ids, [first.pk])
        self.assertEqual(cache.get(first_cache_key), [first.pk])

        second = Category.objects.create(name="缓存分类二")
        second_cache_key = _active_category_ids_cache_key()

        self.assertNotEqual(first_cache_key, second_cache_key)
        self.assertIsNone(cache.get(second_cache_key))
        self.assertEqual(get_active_category_ids(), [first.pk, second.pk])
        self.assertEqual(cache.get(second_cache_key), [first.pk, second.pk])

    def test_latest_private_message_window_is_cached_and_invalidated_on_create(self):
        buyer = User.objects.create_user(
            username="cachebuyer",
            email="cachebuyer@example.com",
            password="StrongPass123",
        )
        seller = User.objects.create_user(
            username="cachesell",
            email="cacheseller@example.com",
            password="StrongPass123",
        )
        conversation = get_or_create_conversation(buyer, seller)
        create_private_message(seller, conversation, "缓存前消息")

        messages = get_conversation_message_window(conversation, latest=True)
        cache_key = _latest_message_window_cache_key(conversation.pk)

        self.assertEqual([message.content for message in messages], ["缓存前消息"])
        self.assertEqual(cache.get(cache_key), [messages[0].pk])

        create_private_message(buyer, conversation, "缓存失效消息")

        self.assertIsNone(cache.get(cache_key))


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
)
class PrivateMessageConsumerTest(MessagingTestMixin, TransactionTestCase):
    def setUp(self):
        suffix = uuid4().hex[:4]
        self.seller = User.objects.create_user(
            username=f"异步卖家{suffix}",
            email=f"async-seller-{suffix}@example.com",
            password="StrongPass123",
        )
        self.buyer = User.objects.create_user(
            username=f"异步买家{suffix}",
            email=f"async-buyer-{suffix}@example.com",
            password="StrongPass123",
        )
        self.other_user = User.objects.create_user(
            username=f"异步路人{suffix}",
            email=f"async-other-{suffix}@example.com",
            password="StrongPass123",
        )

    async def test_participant_can_send_message_over_websocket(self):
        conversation = await self._get_or_create_conversation()
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/messages/{conversation.pk}/",
        )
        communicator.scope["user"] = self.buyer

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        await communicator.send_json_to({"content": "WebSocket 私信"})
        response = await communicator.receive_json_from()

        self.assertEqual(response["type"], "message")
        self.assertEqual(response["message"]["content"], "WebSocket 私信")
        count = await self._message_count("WebSocket 私信")
        self.assertEqual(count, 1)
        await communicator.disconnect()

    async def test_non_participant_connection_is_rejected(self):
        conversation = await self._get_or_create_conversation()
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/messages/{conversation.pk}/",
        )
        communicator.scope["user"] = self.other_user

        connected, _ = await communicator.connect()

        self.assertFalse(connected)

    @database_sync_to_async
    def _get_or_create_conversation(self):
        return get_or_create_conversation(self.buyer, self.seller)

    @database_sync_to_async
    def _message_count(self, content):
        return PrivateMessage.objects.filter(content=content).count()


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
        self.assertEqual(list_response.json()[0]["content"], "历史消息")
        self.assertEqual(send_response.status_code, 201)
        body = send_response.json()
        self.assertEqual(body["content"], "HTTP API 私信")
        self.assertEqual(body["sender"]["id"], self.buyer.id)
        self.assertEqual(body["sender_id"], self.buyer.id)
        self.assertEqual(PrivateMessage.objects.filter(content="HTTP API 私信").count(), 1)

    def test_messages_api_defaults_to_latest_window_for_chat_entry(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        for index in range(25):
            create_private_message(self.seller, conversation, f"历史消息 {index:02d}")

        response = self.client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        contents = [item["content"] for item in response.json()]
        self.assertEqual(len(contents), 20)
        self.assertEqual(contents[0], "历史消息 05")
        self.assertEqual(contents[-1], "历史消息 24")

    def test_messages_api_returns_previous_window_before_id(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        messages = [
            create_private_message(self.seller, conversation, f"翻页消息 {index}")
            for index in range(5)
        ]

        response = self.client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"before_id": messages[3].pk, "limit": 2},
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["content"] for item in response.json()],
            ["翻页消息 1", "翻页消息 2"],
        )

    def test_messages_api_returns_incremental_window_after_id(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        first = create_private_message(self.seller, conversation, "已有消息")
        create_private_message(self.buyer, conversation, "新增消息一")
        create_private_message(self.seller, conversation, "新增消息二")

        response = self.client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"after_id": first.pk},
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["content"] for item in response.json()],
            ["新增消息一", "新增消息二"],
        )

    def test_messages_api_rejects_conflicting_window_params(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)

        response = self.client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"before_id": 1, "after_id": 2},
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 400)

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

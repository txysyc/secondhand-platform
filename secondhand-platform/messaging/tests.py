from decimal import Decimal
from uuid import uuid4

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Listing
from catalog.selectors import CACHE_KEY_ACTIVE_CATEGORY_IDS, get_active_category_ids
from messaging.admin import ConversationAdmin, PrivateMessageAdmin
from messaging.models import Conversation, PrivateMessage
from messaging.routing import websocket_urlpatterns
from messaging.selectors import get_conversation_for_user, get_user_conversations
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


class MessagingViewTest(MessagingTestMixin, TestCase):
    def test_guest_private_message_pages_require_login(self):
        response = self.client.get(reverse("messaging:conversation_list"))

        self.assertRedirects(
            response,
            f"{reverse('users:login')}?next={reverse('messaging:conversation_list')}",
        )

    def test_listing_detail_and_public_profile_show_contact_entry(self):
        self.client.force_login(self.buyer)

        detail_response = self.client.get(
            reverse("catalog:listing_detail", kwargs={"pk": self.listing.pk})
        )
        profile_response = self.client.get(
            reverse("public_profile", kwargs={"user_id": self.seller.pk})
        )

        self.assertContains(detail_response, "联系卖家")
        self.assertContains(
            detail_response,
            reverse("messaging:start_conversation", kwargs={"user_id": self.seller.pk}),
        )
        self.assertContains(profile_response, "联系卖家")

    def test_start_conversation_redirects_to_detail(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("messaging:start_conversation", kwargs={"user_id": self.seller.pk})
        )

        conversation = Conversation.objects.get()
        self.assertRedirects(
            response,
            reverse("messaging:conversation_detail", kwargs={"pk": conversation.pk}),
        )

    def test_conversation_list_redirects_to_latest_conversation(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        create_private_message(self.seller, conversation, "列表预览消息")
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("messaging:conversation_list"))

        self.assertRedirects(
            response,
            reverse("messaging:conversation_detail", kwargs={"pk": conversation.pk}),
        )

    def test_conversation_detail_renders_messages_and_rejects_non_participant(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        create_private_message(self.seller, conversation, "历史私信")
        self.client.force_login(self.buyer)

        response = self.client.get(
            reverse("messaging:conversation_detail", kwargs={"pk": conversation.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "历史私信")
        self.assertContains(response, "卖家昵称")
        self.assertContains(response, "最近会话")
        self.assertIn("conversations", response.context)
        self.assertEqual(list(response.context["conversations"]), [conversation])

        self.client.force_login(self.other_user)
        response = self.client.get(
            reverse("messaging:conversation_detail", kwargs={"pk": conversation.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_http_post_creates_message_as_fallback(self):
        conversation = get_or_create_conversation(self.buyer, self.seller)
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("messaging:conversation_detail", kwargs={"pk": conversation.pk}),
            {"content": "HTTP 兜底消息"},
        )

        self.assertRedirects(
            response,
            reverse("messaging:conversation_detail", kwargs={"pk": conversation.pk}),
        )
        self.assertTrue(
            PrivateMessage.objects.filter(content="HTTP 兜底消息").exists()
        )


class RedisCacheSelectorTest(TestCase):
    def setUp(self):
        cache.clear()
        Category.objects.all().delete()

    def test_active_category_ids_are_cached_and_invalidated_on_save(self):
        first = Category.objects.create(name="缓存分类一")
        ids = get_active_category_ids()

        self.assertEqual(ids, [first.pk])
        self.assertEqual(cache.get(CACHE_KEY_ACTIVE_CATEGORY_IDS), [first.pk])

        second = Category.objects.create(name="缓存分类二")

        self.assertIsNone(cache.get(CACHE_KEY_ACTIVE_CATEGORY_IDS))
        self.assertEqual(get_active_category_ids(), [first.pk, second.pk])


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

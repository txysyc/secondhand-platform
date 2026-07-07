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
def messaging_context():
    """构造私信服务和选择器测试需要的基础用户与商品。"""

    seller = User.objects.create_user(
        username="私信卖家",
        email="message-seller@example.com",
        password="StrongPass123",
    )
    buyer = User.objects.create_user(
        username="私信买家",
        email="message-buyer@example.com",
        password="StrongPass123",
    )
    other_user = User.objects.create_user(
        username="私信路人",
        email="message-other@example.com",
        password="StrongPass123",
    )
    seller.profile.nickname = "卖家昵称"
    seller.profile.save(update_fields=["nickname", "updated_at"])
    category = Category.objects.create(name="私信分类")
    listing = Listing.objects.create(
        owner=seller,
        category=category,
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
    return {
        "seller": seller,
        "buyer": buyer,
        "other_user": other_user,
        "category": category,
        "listing": listing,
    }


@pytest.fixture
def messaging_api_users():
    """构造私信 HTTP API 测试用户。"""

    return {
        "buyer": User.objects.create_user(
            username="msgbuyer",
            email="msgbuyer@example.com",
            password="StrongPass123",
        ),
        "seller": User.objects.create_user(
            username="msgseller",
            email="msgseller@example.com",
            password="StrongPass123",
        ),
        "other": User.objects.create_user(
            username="msgother",
            email="msgother@example.com",
            password="StrongPass123",
        ),
    }


@pytest.fixture
def clear_cache():
    """清理缓存和分类表，隔离缓存选择器测试。"""

    cache.clear()
    Category.objects.all().delete()


class TestConversationService:
    """私信会话与消息服务测试。"""

    def test_get_or_create_conversation_uses_single_ordered_pair(self, messaging_context):
        buyer = messaging_context["buyer"]
        seller = messaging_context["seller"]

        first = get_or_create_conversation(buyer, seller)
        second = get_or_create_conversation(seller, buyer)

        assert first == second
        assert first.participant_a_id < first.participant_b_id
        assert Conversation.objects.count() == 1

    def test_cannot_start_conversation_with_self_or_inactive_user(self, messaging_context):
        buyer = messaging_context["buyer"]
        inactive = User.objects.create_user(
            username="停用用户",
            email="inactive-message@example.com",
            password="StrongPass123",
            is_active=False,
        )

        with pytest.raises(ValidationError, match="不能给自己发送私信"):
            get_or_create_conversation(buyer, buyer)
        with pytest.raises(ValidationError, match="目标用户不可用"):
            get_or_create_conversation(buyer, inactive)

    def test_create_private_message_requires_participant_and_valid_content(
        self,
        messaging_context,
    ):
        buyer = messaging_context["buyer"]
        seller = messaging_context["seller"]
        other_user = messaging_context["other_user"]
        conversation = get_or_create_conversation(buyer, seller)

        with pytest.raises(PermissionDenied):
            create_private_message(other_user, conversation, "路人插话")
        with pytest.raises(ValidationError, match="消息内容不能为空"):
            create_private_message(buyer, conversation, "   ")
        with pytest.raises(ValidationError, match="消息内容不能超过 1000 个字符"):
            create_private_message(buyer, conversation, "x" * 1001)

        message = create_private_message(buyer, conversation, "请问还在吗？")

        assert message.sender == buyer
        assert message.content == "请问还在吗？"

    def test_mark_conversation_read_updates_only_received_messages(self, messaging_context):
        buyer = messaging_context["buyer"]
        seller = messaging_context["seller"]
        conversation = get_or_create_conversation(buyer, seller)
        own_message = create_private_message(buyer, conversation, "我发出的")
        received_message = create_private_message(seller, conversation, "我收到的")

        updated = mark_conversation_read(buyer, conversation)

        assert updated == 1
        own_message.refresh_from_db()
        received_message.refresh_from_db()
        assert own_message.read_at is None
        assert received_message.read_at is not None


class TestConversationSelector:
    """私信会话选择器测试。"""

    def test_get_user_conversations_returns_only_participant_conversations_with_unread_count(
        self,
        messaging_context,
    ):
        buyer = messaging_context["buyer"]
        seller = messaging_context["seller"]
        other_user = messaging_context["other_user"]
        target = get_or_create_conversation(buyer, seller)
        create_private_message(seller, target, "未读消息")
        other = get_or_create_conversation(seller, other_user)
        create_private_message(seller, other, "无关消息")

        conversations = list(get_user_conversations(buyer))

        assert conversations == [target]
        assert conversations[0].unread_count == 1
        assert conversations[0].latest_message_content == "未读消息"
        assert conversations[0].latest_message_created_at is not None

    def test_get_conversation_for_user_rejects_non_participant(self, messaging_context):
        buyer = messaging_context["buyer"]
        seller = messaging_context["seller"]
        other_user = messaging_context["other_user"]
        conversation = get_or_create_conversation(buyer, seller)

        with pytest.raises(Conversation.DoesNotExist):
            get_conversation_for_user(other_user, conversation.pk)


class TestMessagingAdmin:
    """私信后台注册与展示测试。"""

    def test_messaging_models_are_registered_to_admin(self):
        assert isinstance(site._registry[Conversation], ConversationAdmin)
        assert isinstance(site._registry[PrivateMessage], PrivateMessageAdmin)

    def test_admin_uses_summary_instead_of_full_message_in_list_display(
        self,
        messaging_context,
    ):
        buyer = messaging_context["buyer"]
        seller = messaging_context["seller"]
        message_admin = site._registry[PrivateMessage]
        conversation = get_or_create_conversation(buyer, seller)
        message = create_private_message(
            buyer,
            conversation,
            "这是一条超过二十个字符的私信内容，用于验证摘要展示",
        )

        assert message_admin.short_content(message) == message.content[:20]


class TestRedisCacheSelector:
    """缓存选择器测试。"""

    def test_active_category_ids_are_cached_and_invalidated_on_save(self, clear_cache):
        first = Category.objects.create(name="缓存分类一")
        ids = get_active_category_ids()
        first_cache_key = _active_category_ids_cache_key()

        assert ids == [first.pk]
        assert cache.get(first_cache_key) == [first.pk]

        second = Category.objects.create(name="缓存分类二")
        second_cache_key = _active_category_ids_cache_key()

        assert first_cache_key != second_cache_key
        assert cache.get(second_cache_key) is None
        assert get_active_category_ids() == [first.pk, second.pk]
        assert cache.get(second_cache_key) == [first.pk, second.pk]

    def test_latest_private_message_window_is_cached_and_invalidated_on_create(
        self,
        clear_cache,
    ):
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

        assert [message.content for message in messages] == ["缓存前消息"]
        assert cache.get(cache_key) == [messages[0].pk]

        create_private_message(buyer, conversation, "缓存失效消息")

        assert cache.get(cache_key) is None


class TestMessagingApi:
    """私信 HTTP API 测试。"""

    def test_conversation_list_requires_login(self, api_client):
        response = api_client.get(reverse("api:messaging_conversations"))

        assert response.status_code == 401

    def test_start_conversation_creates_or_reuses_pair(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        first_response = api_client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": seller.id},
            format="json",
            **auth_headers(buyer),
        )
        second_response = api_client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": seller.id},
            format="json",
            **auth_headers(buyer),
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 201
        assert first_response.json()["id"] == second_response.json()["id"]
        assert Conversation.objects.count() == 1

    def test_start_conversation_rejects_self_and_inactive_target(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        inactive = User.objects.create_user(
            username="inactive",
            email="inactive-msg@example.com",
            password="StrongPass123",
            is_active=False,
        )

        self_response = api_client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": buyer.id},
            format="json",
            **auth_headers(buyer),
        )
        inactive_response = api_client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": inactive.id},
            format="json",
            **auth_headers(buyer),
        )

        assert self_response.status_code == 400
        assert self_response.json()["message"] == "不能给自己发送私信"
        assert inactive_response.status_code == 400

    def test_conversation_list_includes_unread_and_latest_message(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        other = messaging_api_users["other"]
        conversation = get_or_create_conversation(buyer, seller)
        create_private_message(seller, conversation, "未读 API 消息")
        other_conversation = get_or_create_conversation(seller, other)
        create_private_message(seller, other_conversation, "无关消息")

        response = api_client.get(
            reverse("api:messaging_conversations"),
            **auth_headers(buyer),
        )

        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["id"] == conversation.id
        assert results[0]["unread_count"] == 1
        assert results[0]["latest_message_content"] == "未读 API 消息"
        assert results[0]["other_participant"]["id"] == seller.id

    def test_non_participant_cannot_access_conversation_or_messages(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        other = messaging_api_users["other"]
        conversation = get_or_create_conversation(buyer, seller)

        detail_response = api_client.get(
            reverse("api:messaging_conversation_detail", kwargs={"pk": conversation.id}),
            **auth_headers(other),
        )
        messages_response = api_client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            **auth_headers(other),
        )

        assert detail_response.status_code == 403
        assert messages_response.status_code == 403

    def test_messages_api_lists_and_sends_with_shared_payload_shape(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        conversation = get_or_create_conversation(buyer, seller)
        create_private_message(seller, conversation, "历史消息")

        list_response = api_client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            **auth_headers(buyer),
        )
        send_response = api_client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"content": "  HTTP API 私信  "},
            format="json",
            **auth_headers(buyer),
        )

        assert list_response.status_code == 200
        assert list_response.json()[0]["content"] == "历史消息"
        assert send_response.status_code == 201
        body = send_response.json()
        assert body["content"] == "HTTP API 私信"
        assert body["sender"]["id"] == buyer.id
        assert body["sender_id"] == buyer.id
        assert PrivateMessage.objects.filter(content="HTTP API 私信").count() == 1

    def test_messages_api_defaults_to_latest_window_for_chat_entry(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        conversation = get_or_create_conversation(buyer, seller)
        for index in range(25):
            create_private_message(seller, conversation, f"历史消息 {index:02d}")

        response = api_client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            **auth_headers(buyer),
        )

        assert response.status_code == 200
        contents = [item["content"] for item in response.json()]
        assert len(contents) == 20
        assert contents[0] == "历史消息 05"
        assert contents[-1] == "历史消息 24"

    def test_messages_api_returns_previous_window_before_id(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        conversation = get_or_create_conversation(buyer, seller)
        messages = [
            create_private_message(seller, conversation, f"翻页消息 {index}")
            for index in range(5)
        ]

        response = api_client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"before_id": messages[3].pk, "limit": 2},
            **auth_headers(buyer),
        )

        assert response.status_code == 200
        assert [item["content"] for item in response.json()] == [
            "翻页消息 1",
            "翻页消息 2",
        ]

    def test_messages_api_returns_incremental_window_after_id(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        conversation = get_or_create_conversation(buyer, seller)
        first = create_private_message(seller, conversation, "已有消息")
        create_private_message(buyer, conversation, "新增消息一")
        create_private_message(seller, conversation, "新增消息二")

        response = api_client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"after_id": first.pk},
            **auth_headers(buyer),
        )

        assert response.status_code == 200
        assert [item["content"] for item in response.json()] == [
            "新增消息一",
            "新增消息二",
        ]

    def test_messages_api_rejects_conflicting_window_params(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        conversation = get_or_create_conversation(buyer, seller)

        response = api_client.get(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"before_id": 1, "after_id": 2},
            **auth_headers(buyer),
        )

        assert response.status_code == 400

    def test_send_message_rejects_blank_and_overlong_content(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        conversation = get_or_create_conversation(buyer, seller)

        blank_response = api_client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"content": "   "},
            format="json",
            **auth_headers(buyer),
        )
        long_response = api_client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation.id}),
            data={"content": "x" * 1001},
            format="json",
            **auth_headers(buyer),
        )

        assert blank_response.status_code == 400
        assert blank_response.json()["message"] == "消息内容不能为空"
        assert long_response.status_code == 400

    def test_mark_conversation_read_only_updates_received_messages(
        self,
        api_client,
        auth_headers,
        messaging_api_users,
    ):
        buyer = messaging_api_users["buyer"]
        seller = messaging_api_users["seller"]
        conversation = get_or_create_conversation(buyer, seller)
        own = create_private_message(buyer, conversation, "自己发出的")
        received = create_private_message(seller, conversation, "收到的")

        response = api_client.post(
            reverse("api:messaging_conversation_read", kwargs={"pk": conversation.id}),
            **auth_headers(buyer),
        )

        assert response.status_code == 200
        assert response.json()["updated_count"] == 1
        own.refresh_from_db()
        received.refresh_from_db()
        assert own.read_at is None
        assert received.read_at is not None


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

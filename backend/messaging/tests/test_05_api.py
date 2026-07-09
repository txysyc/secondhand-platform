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
        assert list_response.json()["results"][0]["content"] == "历史消息"
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
        body = response.json()
        contents = [item["content"] for item in body["results"]]
        assert len(contents) == 20
        assert contents[0] == "历史消息 05"
        assert contents[-1] == "历史消息 24"
        assert body["before_cursor"] is not None
        assert body["after_cursor"] is not None
        assert body["has_more_before"] is True

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
        body = response.json()
        assert [item["content"] for item in body["results"]] == [
            "翻页消息 1",
            "翻页消息 2",
        ]
        assert body["has_more_before"] is True
        assert body["after_cursor"] == messages[2].pk

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
        body = response.json()
        assert [item["content"] for item in body["results"]] == [
            "新增消息一",
            "新增消息二",
        ]
        assert body["before_cursor"] is not None
        assert body["has_more_after"] is False

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



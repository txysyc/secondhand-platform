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



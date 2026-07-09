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
def clear_cache():
    """清理缓存和分类表，隔离缓存选择器测试。"""

    cache.clear()
    Category.objects.all().delete()



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



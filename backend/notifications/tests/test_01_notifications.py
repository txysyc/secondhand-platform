"""站内通知 pytest 测试。"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from catalog.models import Category, Listing
from interactions.models import Comment
from interactions.services import create_comment, create_reply
from notifications.models import Notification
from notifications.routing import websocket_urlpatterns
from notifications.services import create_notification, mark_notification_read
from orders.models import Order
from orders.services import (
    confirm_order_delivery,
    confirm_order_receipt,
    create_order,
    pay_order,
)
from users.models import UserAddress


pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def notification_context():
    """构造通知测试需要的用户、分类、商品和收货地址。"""

    seller = User.objects.create_user(
        username="notif卖家",
        email="notif-seller@example.com",
        password="StrongPass123",
    )
    buyer = User.objects.create_user(
        username="notif买家",
        email="notif-buyer@example.com",
        password="StrongPass123",
    )
    other = User.objects.create_user(
        username="notif路人",
        email="notif-other@example.com",
        password="StrongPass123",
    )
    category = Category.objects.create(name="通知分类")
    listing = Listing.objects.create(
        owner=seller,
        category=category,
        title="通知商品",
        item_type=Listing.ItemType.PHYSICAL,
        status=Listing.Status.ACTIVE,
        price=Decimal("99.00"),
        condition=Listing.Condition.GOOD,
        description="通知商品描述",
        delivery_notes="面交",
        physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
        published_at=timezone.now(),
    )
    address = UserAddress.objects.create(
        user=buyer,
        recipient_name="通知买家",
        phone="13800138000",
        province="广东省",
        city="深圳市",
        district="南山区",
        detail_address="通知地址1号",
        is_default=True,
    )
    return {
        "seller": seller,
        "buyer": buyer,
        "other": other,
        "category": category,
        "listing": listing,
        "address": address,
    }


class TestNotificationServiceAndApi:
    """站内通知服务与 HTTP API 测试。"""

    def test_create_notification_skips_self_and_inactive_recipient(
        self,
        notification_context,
    ):
        """通知服务跳过自己通知自己和未激活接收者。"""

        seller = notification_context["seller"]
        inactive = User.objects.create_user(
            username="停用通知",
            email="inactive-notification@example.com",
            password="StrongPass123",
            is_active=False,
        )

        create_notification(
            recipient=seller,
            actor=seller,
            type=Notification.NotificationType.LISTING_COMMENTED,
            title="自己评论",
            content="自己评论自己的商品",
            target_type=Notification.TargetType.LISTING,
            target_id=notification_context["listing"].pk,
            target_url=f"/listings/{notification_context['listing'].pk}",
        )
        create_notification(
            recipient=inactive,
            actor=seller,
            type=Notification.NotificationType.LISTING_COMMENTED,
            title="停用用户",
            content="停用用户不接收通知",
            target_type=Notification.TargetType.LISTING,
            target_id=notification_context["listing"].pk,
            target_url=f"/listings/{notification_context['listing'].pk}",
        )

        assert Notification.objects.count() == 0

    def test_comment_and_reply_create_expected_notifications(
        self,
        notification_context,
        django_capture_on_commit_callbacks,
    ):
        """评论和回复会给对应用户创建通知。"""

        listing = notification_context["listing"]
        buyer = notification_context["buyer"]
        seller = notification_context["seller"]

        with django_capture_on_commit_callbacks(execute=True):
            comment = create_comment(buyer, listing, "请问还在吗")
            reply = create_reply(seller, comment, "还在")

        listing_notification = Notification.objects.get(
            type=Notification.NotificationType.LISTING_COMMENTED
        )
        reply_notification = Notification.objects.get(
            type=Notification.NotificationType.COMMENT_REPLIED
        )
        assert listing_notification.recipient == seller
        assert listing_notification.actor == buyer
        assert listing_notification.payload["comment_id"] == comment.pk
        assert reply_notification.recipient == buyer
        assert reply_notification.actor == seller
        assert reply_notification.payload["reply_id"] == reply.pk

    def test_order_lifecycle_creates_expected_notifications(
        self,
        notification_context,
        django_capture_on_commit_callbacks,
    ):
        """订单创建、支付、发货和完成会创建对应通知。"""

        buyer = notification_context["buyer"]
        seller = notification_context["seller"]
        listing = notification_context["listing"]
        address = notification_context["address"]

        with django_capture_on_commit_callbacks(execute=True):
            order = create_order(buyer, listing, address_id=address.pk)
            pay_order(buyer, order.pk)
            confirm_order_delivery(seller, order.pk)
            confirm_order_receipt(buyer, order.pk)

        types = list(
            Notification.objects.order_by("created_at").values_list("type", flat=True)
        )
        assert types == [
            Notification.NotificationType.ORDER_CREATED,
            Notification.NotificationType.ORDER_PAID,
            Notification.NotificationType.ORDER_DELIVERED,
            Notification.NotificationType.ORDER_COMPLETED,
        ]
        assert Notification.objects.filter(recipient=seller).count() == 3
        assert Notification.objects.filter(recipient=buyer).count() == 1

    def test_notification_list_count_and_read_api(
        self,
        api_client,
        auth_headers,
        notification_context,
    ):
        """通知列表、未读数、单条已读和全部已读接口可用。"""

        buyer = notification_context["buyer"]
        other = notification_context["other"]
        first = create_notification(
            recipient=buyer,
            actor=other,
            type=Notification.NotificationType.LISTING_COMMENTED,
            title="第一条通知",
            content="第一条通知内容",
            target_type=Notification.TargetType.LISTING,
            target_id=notification_context["listing"].pk,
            target_url=f"/listings/{notification_context['listing'].pk}",
        )
        create_notification(
            recipient=buyer,
            actor=other,
            type=Notification.NotificationType.COMMENT_REPLIED,
            title="第二条通知",
            content="第二条通知内容",
            target_type=Notification.TargetType.LISTING,
            target_id=notification_context["listing"].pk,
            target_url=f"/listings/{notification_context['listing'].pk}",
        )

        list_response = api_client.get(
            reverse("api:notifications"),
            {"status": "unread"},
            **auth_headers(buyer),
        )
        count_response = api_client.get(
            reverse("api:notifications_unread_count"),
            **auth_headers(buyer),
        )
        read_response = api_client.post(
            reverse("api:notifications_read", kwargs={"pk": first.pk}),
            **auth_headers(buyer),
        )
        read_all_response = api_client.post(
            reverse("api:notifications_read_all"),
            **auth_headers(buyer),
        )

        assert list_response.status_code == 200
        assert list_response.json()["count"] == 2
        assert count_response.json()["unread_count"] == 2
        assert read_response.status_code == 200
        assert read_response.json()["is_read"] is True
        assert read_all_response.json()["updated_count"] == 1
        assert Notification.objects.filter(recipient=buyer, read_at__isnull=True).count() == 0

    def test_other_user_cannot_read_notification(
        self,
        api_client,
        auth_headers,
        notification_context,
    ):
        """用户不能把他人的通知标记已读。"""

        notification = create_notification(
            recipient=notification_context["buyer"],
            actor=notification_context["seller"],
            type=Notification.NotificationType.ORDER_CREATED,
            title="订单通知",
            content="订单通知内容",
            target_type=Notification.TargetType.ORDER,
            target_id=1,
            target_url="/orders/1",
        )

        response = api_client.post(
            reverse("api:notifications_read", kwargs={"pk": notification.pk}),
            **auth_headers(notification_context["other"]),
        )

        assert response.status_code == 404

    def test_notification_status_filter_rejects_invalid_value(
        self,
        api_client,
        auth_headers,
        notification_context,
    ):
        """非法通知状态筛选返回 400。"""

        response = api_client.get(
            reverse("api:notifications"),
            {"status": "unknown"},
            **auth_headers(notification_context["buyer"]),
        )

        assert response.status_code == 400
        assert response.json()["message"] == "通知状态筛选参数无效"


@pytest.fixture
def websocket_settings(settings):
    """使用内存 channel layer 隔离通知 WebSocket 测试。"""

    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }


@database_sync_to_async
def _create_websocket_user():
    """在线程池中创建通知 WebSocket 测试用户。"""

    suffix = uuid4().hex[:4]
    return User.objects.create_user(
        username=f"通知ws{suffix}",
        email=f"notification-ws-{suffix}@example.com",
        password="StrongPass123",
    )


@database_sync_to_async
def _create_websocket_notification(user):
    """在线程池中创建通知并触发 WebSocket 推送。"""

    return create_notification(
        recipient=user,
        actor=None,
        type=Notification.NotificationType.ORDER_PAID,
        title="实时通知",
        content="实时通知内容",
        target_type=Notification.TargetType.ORDER,
        target_id=1,
        target_url="/orders/1",
    )


@database_sync_to_async
def _mark_websocket_notification_read(user, notification):
    """在线程池中标记通知已读并触发未读数推送。"""

    return mark_notification_read(user, notification)


@database_sync_to_async
def _access_token_for(user):
    """在线程池中签发 access token。"""

    return str(AccessToken.for_user(user))


@pytest.mark.django_db(transaction=True)
class TestNotificationConsumer:
    """站内通知 WebSocket Consumer 测试。"""

    async def test_authenticated_user_receives_created_notification(
        self,
        websocket_settings,
    ):
        """登录用户能收到自己的实时通知推送。"""

        user = await _create_websocket_user()
        token = await _access_token_for(user)
        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            f"/ws/notifications/?token={token}",
        )
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        assert connected is True

        notification = await _create_websocket_notification(user)
        response = await communicator.receive_json_from()

        assert response["type"] == "notification.created"
        assert response["notification"]["title"] == "实时通知"
        assert response["unread_count"] == 1

        await _mark_websocket_notification_read(user, notification)
        unread_response = await communicator.receive_json_from()

        assert unread_response["type"] == "notification.unread_count"
        assert unread_response["unread_count"] == 0
        await communicator.disconnect()

    async def test_anonymous_user_cannot_connect(self, websocket_settings):
        """匿名用户不能建立通知 WebSocket 连接。"""

        communicator = WebsocketCommunicator(
            URLRouter(websocket_urlpatterns),
            "/ws/notifications/",
        )
        communicator.scope["user"] = AnonymousUser()

        connected, _ = await communicator.connect()

        assert connected is False
        await communicator.disconnect()


class TestThrottleApi:
    """阶段四关键接口限流测试。"""

    @pytest.fixture(autouse=True)
    def _setup_throttle(self, settings):
        """降低测试限流频率并清理缓存。"""

        cache.clear()
        settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(
            {
                "auth_register": "1/min",
                "auth_login": "1/min",
                "comment_write": "1/min",
                "message_send": "1/min",
            }
        )

    def test_register_is_throttled(self, api_client):
        """注册接口超出频率后返回 429。"""

        Group.objects.create(name="普通用户组")

        first_response = api_client.post(
            reverse("api:auth_register"),
            data={
                "username": "限流甲",
                "email": "throttle-a@example.com",
                "password": "StrongPass123",
                "password_confirm": "StrongPass123",
            },
            format="json",
        )
        second_response = api_client.post(
            reverse("api:auth_register"),
            data={
                "username": "限流乙",
                "email": "throttle-b@example.com",
                "password": "StrongPass123",
                "password_confirm": "StrongPass123",
            },
            format="json",
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 429
        assert second_response.json()["message"] == "请求过于频繁，请稍后再试。"

    def test_comment_write_is_throttled_but_get_is_not(
        self,
        api_client,
        auth_headers,
        notification_context,
    ):
        """评论 POST 被限流，但评论 GET 不受写接口限流影响。"""

        listing = notification_context["listing"]
        buyer = notification_context["buyer"]
        post_url = reverse("api:listing_comments", kwargs={"listing_id": listing.pk})

        first_response = api_client.post(
            post_url,
            data={"content": "第一条"},
            format="json",
            **auth_headers(buyer),
        )
        second_response = api_client.post(
            post_url,
            data={"content": "第二条"},
            format="json",
            **auth_headers(buyer),
        )
        get_response = api_client.get(post_url, **auth_headers(buyer))

        assert first_response.status_code == 201
        assert second_response.status_code == 429
        assert get_response.status_code == 200

    def test_message_send_is_throttled_per_user(
        self,
        api_client,
        auth_headers,
        notification_context,
    ):
        """发起会话和发送私信共用 message_send 限流，不同用户互不影响。"""

        buyer = notification_context["buyer"]
        seller = notification_context["seller"]
        other = notification_context["other"]
        conversation_response = api_client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": seller.pk},
            format="json",
            **auth_headers(buyer),
        )
        conversation_id = conversation_response.json()["id"]
        first_response = api_client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation_id}),
            data={"content": "第一条私信"},
            format="json",
            **auth_headers(buyer),
        )
        second_response = api_client.post(
            reverse("api:messaging_conversation_messages", kwargs={"pk": conversation_id}),
            data={"content": "第二条私信"},
            format="json",
            **auth_headers(buyer),
        )
        other_conversation_response = api_client.post(
            reverse("api:messaging_conversations"),
            data={"target_user_id": seller.pk},
            format="json",
            **auth_headers(other),
        )

        assert conversation_response.status_code == 201
        assert first_response.status_code == 429
        assert second_response.status_code == 429
        assert other_conversation_response.status_code == 201

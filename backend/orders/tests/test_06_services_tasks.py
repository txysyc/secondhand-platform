from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import Category, Listing, ListingImage
from orders.admin import OrderAdmin
from orders.models import Order
from orders.selectors import get_buyer_orders, get_seller_orders
from orders.services import (
    cancel_expired_pending_orders,
    auto_complete_eligible_physical_order,
    auto_complete_eligible_virtual_order,
    confirm_order_delivery,
    confirm_order_receipt,
    create_order,
    mark_due_physical_orders_signed,
    pay_order,
)
from orders import tasks as order_tasks
from users.models import UserAddress

User = get_user_model()


pytestmark = pytest.mark.django_db

@pytest.mark.django_db(transaction=True)
class TestDeliveryAndReceiptTaskService:
    """模拟签收和自动完成服务测试。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self):
        self.buyer = User.objects.create_user(
            username="任务买家", email="task-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="任务卖家", email="task-seller@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="任务分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="任务商品",
            item_type=item_type,
            status=status,
            price=Decimal("119.00"),
            description="测试描述",
        )

    def _create_order(self, listing=None, status=Order.OrderStatus.AWAITING_RECEIPT, **kwargs):
        listing = listing or self._create_listing()
        defaults = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": listing.title,
            "order_price": listing.price,
            "status": status,
            "payment_deadline": timezone.now() + timedelta(minutes=15),
            "paid_at": timezone.now() - timedelta(days=2),
            "shipped_at": timezone.now() - timedelta(days=2),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_mark_due_physical_orders_signed_only_updates_due_physical_orders(self):
        now = timezone.now()
        due = self._create_order(logistics_signed_due_at=now - timedelta(minutes=1))
        not_due = self._create_order(logistics_signed_due_at=now + timedelta(days=1))
        virtual = self._create_order(
            listing=self._create_listing(item_type=Listing.ItemType.VIRTUAL),
            logistics_signed_due_at=now - timedelta(minutes=1),
        )
        count = mark_due_physical_orders_signed(now=now)
        assert count == 1
        due.refresh_from_db()
        not_due.refresh_from_db()
        virtual.refresh_from_db()
        assert due.status == Order.OrderStatus.SIGNED
        assert due.signed_at is not None
        assert not_due.status == Order.OrderStatus.AWAITING_RECEIPT
        assert virtual.status == Order.OrderStatus.AWAITING_RECEIPT
        due.listing.refresh_from_db()
        assert due.listing.status == Listing.Status.RESERVED

    def test_mark_due_physical_orders_signed_is_idempotent(self):
        now = timezone.now()
        order = self._create_order(logistics_signed_due_at=now - timedelta(minutes=1))
        first = mark_due_physical_orders_signed(now=now)
        order.refresh_from_db()
        signed_at = order.signed_at
        second = mark_due_physical_orders_signed(now=now + timedelta(minutes=5))
        order.refresh_from_db()
        assert first == 1
        assert second == 0
        assert order.signed_at == signed_at

    def test_auto_complete_physical_signed_after_three_days(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=3, minutes=1),
        )
        count = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        assert count == 1
        assert order.status == Order.OrderStatus.COMPLETED
        assert order.completed_at is not None
        assert order.listing.status == Listing.Status.SOLD

    def test_auto_complete_physical_not_before_three_days(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=2, hours=23),
        )
        count = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        assert count == 0
        assert order.status == Order.OrderStatus.SIGNED

    def test_auto_complete_virtual_after_seven_days(self):
        now = timezone.now()
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(
            listing=listing,
            shipped_at=now - timedelta(days=7, minutes=1),
        )
        count = auto_complete_eligible_virtual_order(now=now)
        order.refresh_from_db()
        listing.refresh_from_db()
        assert count == 1
        assert order.status == Order.OrderStatus.COMPLETED
        assert order.completed_at is not None
        assert listing.status == Listing.Status.SOLD

    def test_auto_complete_virtual_not_before_seven_days(self):
        now = timezone.now()
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(
            listing=listing,
            shipped_at=now - timedelta(days=6, hours=23),
        )
        count = auto_complete_eligible_virtual_order(now=now)
        order.refresh_from_db()
        assert count == 0
        assert order.status == Order.OrderStatus.AWAITING_RECEIPT

    def test_auto_complete_is_idempotent(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=3, minutes=1),
        )
        first = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        completed_at = order.completed_at
        second = auto_complete_eligible_physical_order(now=now + timedelta(minutes=5))
        order.refresh_from_db()
        assert first == 1
        assert second == 0
        assert order.completed_at == completed_at

    def test_tasks_return_processed_counts(self):
        with patch.object(order_tasks, "mark_due_physical_orders_signed", return_value=2):
            assert order_tasks.mark_due_physical_orders_signed_task() == 2
        with patch.object(order_tasks, "auto_complete_eligible_physical_order", return_value=1), patch.object(
            order_tasks, "auto_complete_eligible_virtual_order", return_value=3
        ):
            assert order_tasks.auto_complete_eligible_orders_task() == 4


class TestCancelExpiredOrders:
    """cancel_expired_pending_orders 服务层测试。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self):
        self.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="数码产品")
        self.listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_order(self, status, deadline_minutes):
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            status=status,
            payment_deadline=timezone.now() + timedelta(minutes=deadline_minutes),
        )

    def test_cancels_expired_pending_orders(self):
        order = self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        count = cancel_expired_pending_orders()
        assert count == 1
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.CANCELLED
        assert order.cancelled_at is not None

    def test_does_not_cancel_non_expired_orders(self):
        order = self._create_order(Order.OrderStatus.PENDING_PAYMENT, 10)
        count = cancel_expired_pending_orders()
        assert count == 0
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.PENDING_PAYMENT

    def test_does_not_modify_paid_orders(self):
        order = self._create_order(Order.OrderStatus.AWAITING_SHIPMENT, -5)
        count = cancel_expired_pending_orders()
        assert count == 0
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_SHIPMENT

    def test_does_not_modify_already_cancelled_orders(self):
        order = self._create_order(Order.OrderStatus.CANCELLED, -5)
        count = cancel_expired_pending_orders()
        assert count == 0
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.CANCELLED

    def test_idempotent_repeated_execution(self):
        self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        count1 = cancel_expired_pending_orders()
        count2 = cancel_expired_pending_orders()
        assert count1 == 1
        assert count2 == 0

    def test_does_not_modify_listing_status(self):
        self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        cancel_expired_pending_orders()
        self.listing.refresh_from_db()
        assert self.listing.status == Listing.Status.ACTIVE





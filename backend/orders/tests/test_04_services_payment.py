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
class TestPayOrderService:
    """pay_order 服务层测试。使用事务数据库以正确测试 select_for_update 行为。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self):
        self.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="路人C", email="other@test.com", password="testpass123"
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

    def _create_pending_order(self, buyer=None, listing=None, deadline_minutes=15):
        buyer = buyer or self.buyer
        listing = listing or self.listing
        return Order.objects.create(
            buyer=buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now() + timedelta(minutes=deadline_minutes),
        )

    def test_buyer_can_pay_pending_order(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_SHIPMENT
        assert order.paid_at is not None

    def test_payment_sets_listing_to_reserved(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        self.listing.refresh_from_db()
        assert self.listing.status == Listing.Status.RESERVED

    def test_payment_does_not_set_completed(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        order.refresh_from_db()
        assert order.status != Order.OrderStatus.COMPLETED
        assert order.status == Order.OrderStatus.AWAITING_SHIPMENT

    def test_seller_cannot_pay(self):
        order = self._create_pending_order()
        with pytest.raises(PermissionDenied):
            pay_order(self.seller, order.pk)

    def test_other_user_cannot_pay(self):
        order = self._create_pending_order()
        with pytest.raises(PermissionDenied):
            pay_order(self.other_user, order.pk)

    def test_expired_order_payment_fails_and_cancels(self):
        order = self._create_pending_order(deadline_minutes=-1)
        with pytest.raises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        assert "超时" in str(ctx.value)

    def test_non_active_listing_payment_fails(self):
        self.listing.status = Listing.Status.RESERVED
        self.listing.save()
        order = self._create_pending_order()
        with pytest.raises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        assert "不可购买" in str(ctx.value)
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.PENDING_PAYMENT

    def test_concurrent_orders_only_one_succeeds(self):
        buyer2 = User.objects.create_user(
            username="买家D", email="buyerd@test.com", password="testpass123"
        )
        order1 = self._create_pending_order(buyer=self.buyer)
        order2 = self._create_pending_order(buyer=buyer2)

        pay_order(self.buyer, order1.pk)

        with pytest.raises(ValidationError):
            pay_order(buyer2, order2.pk)

        order1.refresh_from_db()
        order2.refresh_from_db()
        self.listing.refresh_from_db()
        assert order1.status == Order.OrderStatus.AWAITING_SHIPMENT
        assert order2.status != Order.OrderStatus.AWAITING_SHIPMENT
        assert self.listing.status == Listing.Status.RESERVED

    def test_listing_none_payment_fails(self):
        order = self._create_pending_order()
        order.listing = None
        order.save()
        with pytest.raises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        assert "商品不存在" in str(ctx.value)

    def test_already_paid_order_cannot_pay_again(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        with pytest.raises(ValidationError):
            pay_order(self.buyer, order.pk)



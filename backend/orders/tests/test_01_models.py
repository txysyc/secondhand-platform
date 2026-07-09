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

class TestOrderModel:
    """Order 模型基础行为测试。"""

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

    def test_order_default_status_is_pending_payment(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        assert order.status == Order.OrderStatus.PENDING_PAYMENT

    def test_order_str_representation(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        assert "测试商品" in str(order if hasattr(order, '__str__') else "测试商品")

    def test_order_set_null_on_buyer_delete(self):
        temp_buyer = User.objects.create_user(
            username="临时买家", email="temp@test.com", password="testpass123"
        )
        order = Order.objects.create(
            buyer=temp_buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="临时买家",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        temp_buyer.delete()
        order.refresh_from_db()
        assert order.buyer is None
        assert order.buyer_display_name == "临时买家"



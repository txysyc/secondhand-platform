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
class TestConfirmOrderDeliveryService:
    """confirm_order_delivery 服务层测试。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self):
        self.buyer = User.objects.create_user(
            username="交付买家", email="delivery-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="交付卖家", email="delivery-seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="交付路人", email="delivery-other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="交付分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="交付商品",
            item_type=item_type,
            status=status,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_order(self, status=Order.OrderStatus.AWAITING_SHIPMENT, listing=None):
        listing = listing or self._create_listing()
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=self.buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=status,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now(),
        )

    def test_seller_can_confirm_physical_delivery(self):
        order = self._create_order()
        before = timezone.now()
        confirm_order_delivery(self.seller, order.pk)
        after = timezone.now()
        order.refresh_from_db()
        order.listing.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_RECEIPT
        assert order.shipped_at is not None
        assert order.listing.status == Listing.Status.RESERVED
        assert order.logistics_signed_due_at is not None
        assert order.logistics_signed_due_at >= order.shipped_at + timedelta(days=1)
        assert order.logistics_signed_due_at <= order.shipped_at + timedelta(days=5)
        assert order.shipped_at >= before

    def test_virtual_delivery_does_not_create_logistics_due_at(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_RECEIPT
        assert order.shipped_at is not None
        assert order.logistics_signed_due_at is None

    def test_buyer_and_other_user_cannot_confirm_delivery(self):
        for user in [self.buyer, self.other_user]:
            order = self._create_order()
            with pytest.raises(PermissionDenied):
                confirm_order_delivery(user, order.pk)
            order.refresh_from_db()
            assert order.status == Order.OrderStatus.AWAITING_SHIPMENT
            assert order.shipped_at is None

    def test_invalid_statuses_cannot_confirm_delivery(self):
        invalid_statuses = [
            Order.OrderStatus.PENDING_PAYMENT,
            Order.OrderStatus.CANCELLED,
            Order.OrderStatus.AWAITING_RECEIPT,
            Order.OrderStatus.SIGNED,
            Order.OrderStatus.COMPLETED,
        ]
        for status in invalid_statuses:
            order = self._create_order(status=status)
            with pytest.raises(ValidationError):
                confirm_order_delivery(self.seller, order.pk)
            order.refresh_from_db()
            assert order.status == status
            assert order.shipped_at is None
            assert order.logistics_signed_due_at is None

    def test_listing_none_cannot_confirm_delivery(self):
        order = self._create_order()
        order.listing = None
        order.save(update_fields=["listing"])
        with pytest.raises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_SHIPMENT
        assert order.shipped_at is None

    def test_non_reserved_listing_cannot_confirm_delivery(self):
        listing = self._create_listing(status=Listing.Status.ACTIVE)
        order = self._create_order(listing=listing)
        with pytest.raises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_SHIPMENT
        assert listing.status == Listing.Status.ACTIVE

    def test_repeated_delivery_confirmation_is_idempotently_rejected(self):
        order = self._create_order()
        confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        shipped_at = order.shipped_at
        logistics_signed_due_at = order.logistics_signed_due_at
        with pytest.raises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_RECEIPT
        assert order.shipped_at == shipped_at
        assert order.logistics_signed_due_at == logistics_signed_due_at


@pytest.mark.django_db(transaction=True)
class TestConfirmOrderReceiptService:
    """confirm_order_receipt 服务层测试。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self):
        self.buyer = User.objects.create_user(
            username="收货买家", email="receipt-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="收货卖家", email="receipt-seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="收货路人", email="receipt-other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="收货分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="收货商品",
            item_type=item_type,
            status=status,
            price=Decimal("109.00"),
            description="测试描述",
        )

    def _create_order(self, status=Order.OrderStatus.AWAITING_RECEIPT, listing=None, **kwargs):
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
            "paid_at": timezone.now() - timedelta(days=1),
            "shipped_at": timezone.now() - timedelta(hours=2),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_buyer_can_complete_virtual_awaiting_receipt_order(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        assert order.status == Order.OrderStatus.COMPLETED
        assert order.completed_at is not None
        assert listing.status == Listing.Status.SOLD

    def test_buyer_can_complete_physical_awaiting_receipt_order(self):
        order = self._create_order(status=Order.OrderStatus.AWAITING_RECEIPT)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        assert order.status == Order.OrderStatus.COMPLETED
        assert order.completed_at is not None
        assert order.listing.status == Listing.Status.SOLD

    def test_buyer_can_complete_physical_signed_order(self):
        order = self._create_order(status=Order.OrderStatus.SIGNED, signed_at=timezone.now())
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        assert order.status == Order.OrderStatus.COMPLETED
        assert order.completed_at is not None
        assert order.listing.status == Listing.Status.SOLD

    def test_seller_and_other_user_cannot_confirm_receipt(self):
        for user in [self.seller, self.other_user]:
            order = self._create_order()
            with pytest.raises(PermissionDenied):
                confirm_order_receipt(user, order.pk)
            order.refresh_from_db()
            assert order.status == Order.OrderStatus.AWAITING_RECEIPT
            assert order.completed_at is None

    def test_invalid_statuses_cannot_confirm_receipt(self):
        for status in [
            Order.OrderStatus.PENDING_PAYMENT,
            Order.OrderStatus.CANCELLED,
            Order.OrderStatus.AWAITING_SHIPMENT,
            Order.OrderStatus.COMPLETED,
        ]:
            order = self._create_order(status=status)
            with pytest.raises(ValidationError):
                confirm_order_receipt(self.buyer, order.pk)
            order.refresh_from_db()
            assert order.status == status
            assert order.completed_at is None

    def test_listing_none_cannot_confirm_receipt(self):
        order = self._create_order()
        order.listing = None
        order.save(update_fields=["listing"])
        with pytest.raises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_RECEIPT
        assert order.completed_at is None

    def test_non_reserved_listing_cannot_confirm_receipt(self):
        listing = self._create_listing(status=Listing.Status.ACTIVE)
        order = self._create_order(listing=listing)
        with pytest.raises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        assert order.status == Order.OrderStatus.AWAITING_RECEIPT
        assert listing.status == Listing.Status.ACTIVE

    def test_repeated_receipt_confirmation_does_not_override_completed_at(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        completed_at = order.completed_at
        with pytest.raises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        assert order.status == Order.OrderStatus.COMPLETED
        assert order.completed_at == completed_at



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

class TestCreateOrderService:
    """create_order 服务层测试。"""

    @pytest.fixture(autouse=True)
    def _setup_context(self):
        self.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="数码产品")
        self.address = UserAddress.objects.create(
            user=self.buyer,
            recipient_name="买家A",
            phone="13800138000",
            province="广东省",
            city="深圳市",
            district="南山区",
            detail_address="科技园1号",
            is_default=True,
        )

    def _create_active_listing(self, **kwargs):
        defaults = {
            "owner": self.seller,
            "category": self.category,
            "title": "测试商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("199.00"),
            "description": "测试描述",
        }
        defaults.update(kwargs)
        return Listing.objects.create(**defaults)

    def test_create_order_success(self):
        listing = self._create_active_listing()
        order = create_order(self.buyer, listing, address_id=self.address.id)

        assert order.status == Order.OrderStatus.PENDING_PAYMENT
        assert order.buyer == self.buyer
        assert order.seller == self.seller
        assert order.listing == listing
        assert order.order_price == Decimal("199.00")
        assert order.listing_title_snapshot == "测试商品"
        assert order.shipping_recipient_name == "买家A"
        assert order.shipping_phone == "13800138000"

    def test_create_order_captures_first_listing_image_snapshot(self):
        listing = self._create_active_listing()
        ListingImage.objects.create(
            listing=listing,
            image="listings/later.png",
            sort_order=2,
        )
        first_image = ListingImage.objects.create(
            listing=listing,
            image="listings/first.png",
            sort_order=1,
        )

        order = create_order(self.buyer, listing, address_id=self.address.id)

        assert order.listing_image_snapshot == first_image.image.url

    def test_create_order_listing_status_unchanged(self):
        listing = self._create_active_listing()
        create_order(self.buyer, listing, address_id=self.address.id)

        listing.refresh_from_db()
        assert listing.status == Listing.Status.ACTIVE

    def test_payment_deadline_is_15_minutes_from_now(self):
        listing = self._create_active_listing()
        before = timezone.now()
        order = create_order(self.buyer, listing, address_id=self.address.id)
        after = timezone.now()

        expected_min = before + timedelta(minutes=15)
        expected_max = after + timedelta(minutes=15)
        assert order.payment_deadline >= expected_min
        assert order.payment_deadline <= expected_max

    def test_buyer_cannot_purchase_own_listing(self):
        listing = self._create_active_listing(owner=self.buyer)

        with pytest.raises(PermissionDenied):
            create_order(self.buyer, listing, address_id=self.address.id)

    def test_cannot_order_non_active_listing(self):
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]:
            listing = self._create_active_listing(status=status)
            with pytest.raises(ValidationError):
                create_order(self.buyer, listing, address_id=self.address.id)

    def test_rejects_duplicate_unexpired_pending_order_for_same_listing(self):
        listing = self._create_active_listing()
        another_buyer = User.objects.create_user(
            username="买家C", email="buyerc@test.com", password="testpass123"
        )
        UserAddress.objects.create(
            user=another_buyer,
            recipient_name="买家C",
            phone="13900139000",
            province="广东省",
            city="广州市",
            district="天河区",
            detail_address="体育西路1号",
            is_default=True,
        )
        order1 = create_order(self.buyer, listing, address_id=self.address.id)

        with pytest.raises(ValidationError):
            create_order(another_buyer, listing, address_id=another_buyer.addresses.first().id)

        assert order1.status == Order.OrderStatus.PENDING_PAYMENT
        assert (
            Order.objects.filter(
                listing=listing,
                status=Order.OrderStatus.PENDING_PAYMENT,
            ).count()
            == 1
        )

    def test_expired_pending_order_does_not_block_new_order(self):
        listing = self._create_active_listing()
        Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=self.buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now() - timedelta(minutes=1),
        )
        another_buyer = User.objects.create_user(
            username="买家C", email="buyerc@test.com", password="testpass123"
        )
        another_address = UserAddress.objects.create(
            user=another_buyer,
            recipient_name="买家C",
            phone="13900139000",
            province="广东省",
            city="广州市",
            district="天河区",
            detail_address="体育西路1号",
            is_default=True,
        )

        order = create_order(another_buyer, listing, address_id=another_address.id)

        assert order.status == Order.OrderStatus.PENDING_PAYMENT

    def test_snapshot_fields_captured_at_creation(self):
        listing = self._create_active_listing(title="原始标题", price=Decimal("50.00"))
        order = create_order(self.buyer, listing, address_id=self.address.id)

        listing.title = "修改后标题"
        listing.price = Decimal("999.00")
        listing.save()

        order.refresh_from_db()
        assert order.listing_title_snapshot == "原始标题"
        assert order.order_price == Decimal("50.00")

    def test_display_name_uses_nickname(self):
        self.buyer.profile.nickname = "买家昵称"
        self.buyer.profile.save()
        self.seller.profile.nickname = "卖家昵称"
        self.seller.profile.save()

        listing = self._create_active_listing()
        order = create_order(self.buyer, listing, address_id=self.address.id)

        assert order.buyer_display_name == "买家昵称"
        assert order.seller_display_name == "卖家昵称"

    def test_physical_order_requires_address(self):
        listing = self._create_active_listing()

        with pytest.raises(ValidationError) as ctx:
            create_order(self.buyer, listing)

        assert "收货地址" in str(ctx.value)

    def test_rejects_other_users_address(self):
        listing = self._create_active_listing()
        other_user = User.objects.create_user(
            username="地址他人", email="addr-other@test.com", password="testpass123"
        )
        other_address = UserAddress.objects.create(
            user=other_user,
            recipient_name="地址他人",
            phone="13700137000",
            province="广东省",
            city="珠海市",
            district="香洲区",
            detail_address="情侣路1号",
        )

        with pytest.raises(ValidationError) as ctx:
            create_order(self.buyer, listing, address_id=other_address.id)

        assert "收货地址不存在" in str(ctx.value)

    def test_virtual_order_ignores_address(self):
        listing = self._create_active_listing(item_type=Listing.ItemType.VIRTUAL)

        order = create_order(self.buyer, listing, address_id=self.address.id)

        assert order.shipping_recipient_name is None



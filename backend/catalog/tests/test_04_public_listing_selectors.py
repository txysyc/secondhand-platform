from decimal import Decimal

import pytest
from io import BytesIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.admin import CategoryAdmin, ListingAdmin
from catalog.filters import ListingFilterSet
from catalog.models import Category, Listing, ListingImage
from catalog.selectors import (
    get_active_categories,
    get_public_listing_queryset,
    get_visible_listing_detail_queryset,
)
from orders.models import Order
from catalog.services import (
    ACTION_RESTORE_ACTIVE,
    ACTION_WITHDRAW,
    change_listing_status,
    delete_listing,
    publish_listing,
)
from users.models import User


pytestmark = pytest.mark.django_db

class TestPublicListingSelector:
    """公开商品列表 selector 测试。"""

    @pytest.fixture(autouse=True)
    def _setup_public_listing_context(self):
        """构造公开商品 selector 测试需要的卖家和分类。"""

        self.user = get_user_model().objects.create_user(
            username="pubseller",
            email="public_seller@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="公开分类")
        self.inactive_category = Category.objects.create(name="停用公开分类", is_active=False)

    def make_listing(self, **overrides):
        data = {
            "owner": self.user,
            "category": self.category,
            "title": "公开商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("30.00"),
            "condition": Listing.Condition.GOOD,
            "description": "公开展示商品",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def test_queryset_only_returns_active_listings_in_active_categories(self):
        active = self.make_listing(title="可公开商品")
        self.make_listing(
            title="停用分类商品",
            category=self.inactive_category,
        )

        listings = list(get_public_listing_queryset())

        assert listings == [active]

    def test_queryset_excludes_non_purchasable_statuses(self):
        active = self.make_listing(title="在售商品", status=Listing.Status.ACTIVE)
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.WITHDRAWN,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
        ]:
            self.make_listing(title=f"{status}商品", status=status)

        listings = list(get_public_listing_queryset())

        assert listings == [active]

    def test_queryset_uses_stable_published_at_and_id_desc_order(self):
        published_at = timezone.now() - timezone.timedelta(days=1)
        older = self.make_listing(
            title="较早商品",
            published_at=published_at - timezone.timedelta(hours=1),
        )
        first_same_time = self.make_listing(title="同时间一号", published_at=published_at)
        second_same_time = self.make_listing(title="同时间二号", published_at=published_at)

        listings = list(get_public_listing_queryset())

        assert listings == [second_same_time, first_same_time, older]

    def test_paid_buyer_can_view_reserved_or_sold_listing_detail_queryset(self):
        buyer = get_user_model().objects.create_user(
            username="paidbuy",
            email="paidbuyer@example.com",
            password="StrongPass123",
        )
        reserved = self.make_listing(title="交易中", status=Listing.Status.RESERVED)
        sold = self.make_listing(title="已完成", status=Listing.Status.SOLD)
        Order.objects.create(
            buyer=buyer,
            seller=self.user,
            listing=reserved,
            buyer_display_name=buyer.username,
            seller_display_name=self.user.username,
            listing_title_snapshot=reserved.title,
            order_price=reserved.price,
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            payment_deadline=timezone.now(),
        )
        Order.objects.create(
            buyer=buyer,
            seller=self.user,
            listing=sold,
            buyer_display_name=buyer.username,
            seller_display_name=self.user.username,
            listing_title_snapshot=sold.title,
            order_price=sold.price,
            status=Order.OrderStatus.COMPLETED,
            payment_deadline=timezone.now(),
        )

        listings = list(get_visible_listing_detail_queryset(buyer))

        assert reserved in listings
        assert sold in listings

    def test_unpaid_buyer_cannot_view_reserved_listing_detail_queryset(self):
        buyer = get_user_model().objects.create_user(
            username="unpaidbuy",
            email="unpaidbuyer@example.com",
            password="StrongPass123",
        )
        reserved = self.make_listing(title="未支付占用", status=Listing.Status.RESERVED)
        Order.objects.create(
            buyer=buyer,
            seller=self.user,
            listing=reserved,
            buyer_display_name=buyer.username,
            seller_display_name=self.user.username,
            listing_title_snapshot=reserved.title,
            order_price=reserved.price,
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now(),
        )

        listings = list(get_visible_listing_detail_queryset(buyer))

        assert reserved not in listings


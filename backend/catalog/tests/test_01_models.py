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


class TestCategoryModel:
    """分类模型基础行为测试。"""

    def test_category_defaults_to_active_and_returns_name(self):
        category = Category.objects.create(name="数码产品")

        assert category.is_active is True
        assert str(category) == "数码产品"

    def test_category_name_must_be_unique(self):
        Category.objects.create(name="图书")

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(name="图书")

    def test_category_can_be_deactivated_without_deletion(self):
        category = Category.objects.create(name="生活用品")

        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])

        category.refresh_from_db()
        assert category.is_active is False
        assert Category.objects.filter(pk=category.pk).exists() is True

class TestListingModel:
    """商品模型基础行为测试。"""

    @pytest.fixture(autouse=True)
    def _setup_listing_model_context(self):
        """构造商品模型测试需要的卖家和分类。"""

        self.user = get_user_model().objects.create_user(
            username="seller",
            email="seller@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="数码产品")

    def create_listing(self, **overrides):
        data = {
            "owner": self.user,
            "category": self.category,
            "title": "二手键盘",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.DRAFT,
            "price": Decimal("199.90"),
            "description": "正常使用痕迹",
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def test_listing_can_be_created_with_custom_user_category_and_decimal_price(self):
        listing = self.create_listing()

        assert listing.owner == self.user
        assert listing.category == self.category
        assert listing.price == Decimal("199.90")
        assert str(listing) == "二手键盘"

    def test_item_type_supports_physical_and_virtual_with_chinese_labels(self):
        physical = self.create_listing(item_type=Listing.ItemType.PHYSICAL)
        virtual = self.create_listing(
            title="虚拟兑换码",
            item_type=Listing.ItemType.VIRTUAL,
            price=Decimal("29.00"),
        )

        assert physical.get_item_type_display() == "实体商品"
        assert virtual.get_item_type_display() == "虚拟商品"

    def test_listing_status_contains_required_lifecycle_values(self):
        required_values = {"draft", "active", "reserved", "sold", "withdrawn"}

        assert required_values.issubset(set(Listing.Status.values)) is True

    def test_listing_owner_field_uses_current_custom_user_model(self):
        field = Listing._meta.get_field("owner")

        assert field.remote_field.model is get_user_model()

    def test_listing_category_and_item_type_are_independent_fields(self):
        listing = self.create_listing(item_type=Listing.ItemType.VIRTUAL)

        assert listing.category.name == "数码产品"
        assert listing.item_type == "virtual"
        assert Category.objects.filter(name="虚拟商品").exists() is False

    def test_listing_price_preserves_two_decimal_places(self):
        listing = self.create_listing(price=Decimal("12.30"))

        listing.refresh_from_db()

        assert listing.price == Decimal("12.30")
        assert abs(listing.price.as_tuple().exponent) == 2

    def test_listing_published_at_defaults_to_none(self):
        listing = self.create_listing()

        assert listing.published_at is None



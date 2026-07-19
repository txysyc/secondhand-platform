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

class TestCatalogAdmin:
    """catalog 后台注册与配置测试。"""

    def test_category_and_listing_are_registered_to_admin_site(self):
        assert isinstance(admin.site._registry[Category], CategoryAdmin)
        assert isinstance(admin.site._registry[Listing], ListingAdmin)

    def test_category_admin_supports_active_filter_and_name_search(self):
        category_admin = admin.site._registry[Category]

        assert list(category_admin.list_display) == [
            "name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        assert "is_active" in category_admin.list_filter
        assert "name" in category_admin.search_fields

    def test_listing_admin_exposes_required_columns_filters_and_search(self):
        listing_admin = admin.site._registry[Listing]

        for field in [
            "title",
            "owner",
            "category",
            "item_type",
            "status",
            "price",
            "published_at",
            "created_at",
            "updated_at",
            "delivery_notes_summary",
        ]:
            assert field in listing_admin.list_display
        assert "delivery_notes" not in listing_admin.list_display

        for field in ["status", "category", "owner", "item_type", "created_at"]:
            assert field in listing_admin.list_filter

        for field in ["title", "description", "owner__username", "category__name"]:
            assert field in listing_admin.search_fields

        assert listing_admin.list_select_related == ["owner", "category"]
        for field in ["created_at", "updated_at", "published_at"]:
            assert field in listing_admin.readonly_fields

    def test_listing_admin_exposes_image_count_and_image_inline(self):
        listing_admin = admin.site._registry[Listing]

        assert "image_count_value" in listing_admin.list_display
        image_inline = next(
            inline for inline in listing_admin.inlines if inline.model is ListingImage
        )
        assert image_inline.max_num == 6

    def test_listing_admin_uses_delivery_notes_summary(self):
        listing_admin = admin.site._registry[Listing]
        listing = Listing(delivery_notes="这是一段超过二十个字符的交付说明用于验证摘要")

        assert listing_admin.delivery_notes_summary(listing) == listing.delivery_notes[0:20]

    def test_superuser_can_open_category_and_listing_admin_changelists(self, client):
        superuser = get_user_model().objects.create_superuser(
            username="catadmin",
            email="catalogadmin@example.com",
            password="StrongPass123",
        )
        client.force_login(superuser)

        category_response = client.get(reverse("admin:catalog_category_changelist"))
        listing_response = client.get(reverse("admin:catalog_listing_changelist"))

        assert category_response.status_code == 200
        assert listing_response.status_code == 200

    def test_regular_user_cannot_open_listing_admin_changelist(self, client):
        user = get_user_model().objects.create_user(
            username="catnorm",
            email="catalognormal@example.com",
            password="StrongPass123",
        )
        client.force_login(user)

        response = client.get(reverse("admin:catalog_listing_changelist"))

        assert response.status_code in [302, 403]



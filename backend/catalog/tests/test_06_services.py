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

class TestChangeListingStatusService:
    """商品状态变更服务测试。"""

    @pytest.fixture(autouse=True)
    def _setup_status_service_context(self):
        """构造商品状态服务测试需要的用户和分类。"""

        self.user = get_user_model().objects.create_user(
            username="stseller",
            email="status_seller@example.com",
            password="StrongPass123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="stother",
            email="status_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="服饰")

    def make_listing(self, **overrides):
        data = {
            "owner": self.user,
            "category": self.category,
            "title": "二手外套",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("99.00"),
            "condition": Listing.Condition.GOOD,
            "description": "九成新",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now() - timezone.timedelta(days=2),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def test_withdraw_active_sets_status_and_advances_updated_at(self):
        listing = self.make_listing(status=Listing.Status.ACTIVE)
        Listing.objects.filter(pk=listing.pk).update(
            updated_at=timezone.now() - timezone.timedelta(seconds=1)
        )
        listing.refresh_from_db()
        baseline_updated_at = listing.updated_at

        result = change_listing_status(self.user, listing, ACTION_WITHDRAW)
        result.refresh_from_db()

        assert result.status == Listing.Status.WITHDRAWN
        assert result.updated_at > baseline_updated_at
        assert result.owner_id == self.user.id
        assert result.published_at is not None

    def test_withdraw_rejects_non_active_statuses(self):
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]:
            listing = self.make_listing(status=status)

            with pytest.raises(ValidationError):
                change_listing_status(self.user, listing, ACTION_WITHDRAW)

            listing.refresh_from_db()
            assert listing.status == status

    def test_restore_active_keeps_published_at_and_returns_to_active(self):
        published_at = timezone.now() - timezone.timedelta(days=5)
        listing = self.make_listing(
            status=Listing.Status.WITHDRAWN, published_at=published_at
        )

        result = change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)
        result.refresh_from_db()

        assert result.status == Listing.Status.ACTIVE
        assert result.published_at == published_at

    def test_restore_active_back_fills_missing_published_at(self):
        listing = self.make_listing(
            status=Listing.Status.WITHDRAWN, published_at=None
        )

        before = timezone.now()
        result = change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)
        result.refresh_from_db()

        assert result.status == Listing.Status.ACTIVE
        assert result.published_at is not None
        assert result.published_at >= before - timezone.timedelta(seconds=1)

    def test_restore_active_blocked_when_category_disabled(self):
        listing = self.make_listing(status=Listing.Status.WITHDRAWN)
        self.category.is_active = False
        self.category.save(update_fields=["is_active", "updated_at"])

        with pytest.raises(ValidationError):
            change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)

        listing.refresh_from_db()
        assert listing.status == Listing.Status.WITHDRAWN

    def test_restore_active_rejects_non_withdrawn_statuses(self):
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.ACTIVE,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
        ]:
            listing = self.make_listing(status=status)

            with pytest.raises(ValidationError):
                change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)

            listing.refresh_from_db()
            assert listing.status == status

    def test_unknown_action_raises_validation_error(self):
        listing = self.make_listing(status=Listing.Status.ACTIVE)

        with pytest.raises(ValidationError):
            change_listing_status(self.user, listing, "mark_sold")
        with pytest.raises(ValidationError):
            change_listing_status(self.user, listing, "")

        listing.refresh_from_db()
        assert listing.status == Listing.Status.ACTIVE

    def test_non_owner_cannot_change_status(self):
        listing = self.make_listing(status=Listing.Status.ACTIVE)

        with pytest.raises(PermissionDenied):
            change_listing_status(self.other_user, listing, ACTION_WITHDRAW)

        listing.refresh_from_db()
        assert listing.status == Listing.Status.ACTIVE

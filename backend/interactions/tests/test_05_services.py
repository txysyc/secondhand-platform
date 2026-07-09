"""interactions 行为服务 pytest 测试。"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from catalog.models import Category, Listing
from interactions.models import ListingFavorite, ListingViewHistory
from interactions.services import (
    MAX_VIEW_HISTORY_PER_USER,
    favorite_listing,
    record_listing_view,
    unfavorite_listing,
)


pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def behavior_service_context():
    """构造收藏和浏览历史服务测试需要的用户、分类和商品。"""

    seller = User.objects.create_user(
        username="bhseller",
        email="behavior_seller@example.com",
        password="StrongPass123",
    )
    buyer = User.objects.create_user(
        username="bhbuyer",
        email="behavior_buyer@example.com",
        password="StrongPass123",
    )
    category = Category.objects.create(name="行为分类")

    def create_listing(**overrides):
        data = {
            "owner": seller,
            "category": category,
            "title": "行为商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("66.00"),
            "condition": Listing.Condition.GOOD,
            "description": "行为描述",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    return {
        "seller": seller,
        "buyer": buyer,
        "category": category,
        "listing": create_listing(),
        "create_listing": create_listing,
    }


class TestListingBehaviorServices:
    """商品收藏和浏览历史服务测试。"""

    def test_favorite_listing_is_idempotent(self, behavior_service_context):
        first = favorite_listing(
            behavior_service_context["buyer"],
            behavior_service_context["listing"],
        )
        second = favorite_listing(
            behavior_service_context["buyer"],
            behavior_service_context["listing"],
        )

        assert first.id == second.id
        assert ListingFavorite.objects.count() == 1

    def test_unfavorite_listing_is_idempotent(self, behavior_service_context):
        favorite_listing(
            behavior_service_context["buyer"],
            behavior_service_context["listing"],
        )

        unfavorite_listing(
            behavior_service_context["buyer"],
            behavior_service_context["listing"].id,
        )
        unfavorite_listing(
            behavior_service_context["buyer"],
            behavior_service_context["listing"].id,
        )

        assert ListingFavorite.objects.count() == 0

    def test_record_listing_view_updates_existing_history(self, behavior_service_context):
        first = record_listing_view(
            behavior_service_context["buyer"],
            behavior_service_context["listing"],
        )
        first_viewed_at = first.viewed_at

        second = record_listing_view(
            behavior_service_context["buyer"],
            behavior_service_context["listing"],
        )

        assert first.id == second.id
        assert second.viewed_at >= first_viewed_at
        assert ListingViewHistory.objects.count() == 1

    def test_record_listing_view_trims_old_history(self, behavior_service_context):
        for index in range(MAX_VIEW_HISTORY_PER_USER + 5):
            listing = behavior_service_context["create_listing"](title=f"历史商品{index}")
            record_listing_view(behavior_service_context["buyer"], listing)

        history_items = list(
            ListingViewHistory.objects.filter(user=behavior_service_context["buyer"])
            .order_by("-viewed_at", "-id")
            .values_list("listing__title", flat=True)
        )

        assert len(history_items) == MAX_VIEW_HISTORY_PER_USER
        assert "历史商品0" not in history_items

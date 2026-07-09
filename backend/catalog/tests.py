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
    apply_public_listing_sort,
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


class TestCategorySelector:
    """分类读取查询测试。"""

    def test_get_active_categories_returns_only_active_categories_in_stable_order(self):
        first = Category.objects.create(name="数码产品")
        Category.objects.create(name="停用分类", is_active=False)
        second = Category.objects.create(name="生活用品")

        categories = list(get_active_categories())

        assert categories == [first, second]
        assert "停用分类" not in [category.name for category in categories]


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

    def test_sort_price_asc(self):
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))

        results = list(apply_public_listing_sort(get_public_listing_queryset(), "price_asc"))

        assert results == [cheap, expensive]

    def test_sort_price_desc(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))

        results = list(apply_public_listing_sort(get_public_listing_queryset(), "price_desc"))

        assert results == [expensive, cheap]

    def test_sort_oldest(self):
        older = self.make_listing(
            title="旧", published_at=timezone.now() - timezone.timedelta(days=2)
        )
        newer = self.make_listing(
            title="新", published_at=timezone.now() - timezone.timedelta(days=1)
        )

        results = list(apply_public_listing_sort(get_public_listing_queryset(), "oldest"))

        assert results == [older, newer]

    def test_unknown_sort_falls_back_to_default(self):
        older = self.make_listing(
            title="旧",
            published_at=timezone.now() - timezone.timedelta(days=2),
        )
        newer = self.make_listing(
            title="新",
            published_at=timezone.now() - timezone.timedelta(days=1),
        )

        results = list(apply_public_listing_sort(get_public_listing_queryset(), "invalid_sort"))

        assert results == [newer, older]


class TestListingFilterSet:
    """公开商品列表 FilterSet 测试。"""

    @pytest.fixture(autouse=True)
    def _setup_listing_filter_context(self):
        """构造公开商品筛选测试需要的卖家和分类。"""

        self.user = get_user_model().objects.create_user(
            username="fltseller",
            email="filter_seller@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="筛选分类")
        self.other_category = Category.objects.create(name="筛选另一分类")
        self.inactive_category = Category.objects.create(name="筛选停用分类", is_active=False)

    def make_listing(self, **overrides):
        """创建默认可公开展示的筛选测试商品。"""

        data = {
            "owner": self.user,
            "category": self.category,
            "title": "筛选商品",
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

    def filter_results(self, params):
        """用公开基础查询执行 FilterSet，并返回筛选后的商品列表。"""

        filterset = ListingFilterSet(data=params, queryset=get_public_listing_queryset())
        assert filterset.is_valid(), filterset.errors
        return list(filterset.qs)

    def test_keyword_matches_title_or_description(self):
        match_title = self.make_listing(title="蓝牙耳机", description="无关描述")
        match_desc = self.make_listing(title="无关标题", description="蓝牙音箱描述")
        no_match = self.make_listing(title="无关标题", description="无关描述")

        results = self.filter_results({"q": " 蓝牙 "})

        assert match_title in results
        assert match_desc in results
        assert no_match not in results

    def test_blank_keyword_equals_no_search(self):
        first = self.make_listing(title="蓝牙耳机")
        second = self.make_listing(title="普通键盘")

        results = self.filter_results({"q": "   "})

        assert first in results
        assert second in results

    def test_too_long_keyword_returns_chinese_error(self):
        filterset = ListingFilterSet(
            data={"q": "蓝" * 51},
            queryset=get_public_listing_queryset(),
        )

        assert filterset.is_valid() is False
        assert "搜索关键词不能超过50个字符" in str(filterset.errors)

    def test_category_filter(self):
        target = self.make_listing(title="目标分类商品", category=self.category)
        other = self.make_listing(title="其他分类商品", category=self.other_category)

        results = self.filter_results({"category": self.category.id})

        assert target in results
        assert other not in results

    def test_item_type_filter(self):
        physical = self.make_listing(title="实体", item_type=Listing.ItemType.PHYSICAL)
        virtual = self.make_listing(title="虚拟", item_type=Listing.ItemType.VIRTUAL)

        results = self.filter_results({"item_type": "virtual"})

        assert physical not in results
        assert virtual in results

    def test_price_range_filter(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        mid = self.make_listing(title="中等", price=Decimal("50.00"))
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))

        results = self.filter_results({"min_price": "20", "max_price": "100"})

        assert cheap not in results
        assert mid in results
        assert expensive not in results

    def test_published_range_filter(self):
        old = self.make_listing(
            title="旧商品",
            published_at=timezone.now() - timezone.timedelta(days=5),
        )
        mid = self.make_listing(
            title="中间商品",
            published_at=timezone.now() - timezone.timedelta(days=2),
        )
        new = self.make_listing(title="新商品", published_at=timezone.now())

        results = self.filter_results({
            "published_after": (timezone.now() - timezone.timedelta(days=3)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "published_before": (timezone.now() - timezone.timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
        })

        assert old not in results
        assert mid in results
        assert new not in results

    def test_published_before_date_includes_whole_day(self):
        target_day = timezone.localdate() - timezone.timedelta(days=1)
        target_time = timezone.make_aware(
            timezone.datetime.combine(target_day, timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )
        target = self.make_listing(
            title="当天商品",
            published_at=target_time.replace(hour=18, minute=30, second=0),
        )

        results = self.filter_results({
            "published_before": target.published_at.strftime("%Y-%m-%d"),
        })

        assert target in results

    def test_invalid_price_or_published_range_returns_chinese_error(self):
        price_filterset = ListingFilterSet(
            data={"min_price": "100", "max_price": "10"},
            queryset=get_public_listing_queryset(),
        )
        time_filterset = ListingFilterSet(
            data={
                "published_after": "2026-05-02T10:00",
                "published_before": "2026-05-01T10:00",
            },
            queryset=get_public_listing_queryset(),
        )

        assert price_filterset.is_valid() is False
        assert "最高价格不得低于最低价格" in str(price_filterset.errors)
        assert time_filterset.is_valid() is False
        assert "发布时间截止不得早于发布时间起始" in str(time_filterset.errors)

    def test_combined_filters(self):
        target = self.make_listing(
            title="蓝牙耳机",
            item_type=Listing.ItemType.PHYSICAL,
            price=Decimal("50.00"),
        )
        wrong_type = self.make_listing(
            title="蓝牙会员",
            item_type=Listing.ItemType.VIRTUAL,
            price=Decimal("50.00"),
        )
        wrong_price = self.make_listing(
            title="蓝牙音箱",
            item_type=Listing.ItemType.PHYSICAL,
            price=Decimal("500.00"),
        )

        results = self.filter_results(
            {
                "q": "蓝牙",
                "item_type": "physical",
                "min_price": "10",
                "max_price": "100",
            }
        )

        assert results == [target]


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
def build_png_image(name="listing.png", size=(16, 16)):
    """构造测试用 PNG 图片。"""

    buffer = BytesIO()
    image = Image.new("RGB", size, color="white")
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

class TestCatalogApi:
    """P3 商品 API 测试。"""

    @pytest.fixture(autouse=True)
    def _setup_catalog_api_context(self, api_client, auth_headers, settings):
        """构造商品 API 测试上下文，并使用内存存储隔离上传文件。"""

        settings.STORAGES = {
            "default": {
                "BACKEND": "django.core.files.storage.InMemoryStorage",
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }
        self.api_client = api_client
        self.auth_headers = auth_headers
        self.seller = User.objects.create_user(
            username="apiseller",
            email="apiseller@example.com",
            password="StrongPass123",
        )
        self.other_user = User.objects.create_user(
            username="apiother",
            email="apiother@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="API数码")
        self.inactive_category = Category.objects.create(
            name="API停用分类",
            is_active=False,
        )

    def listing_payload(self, **overrides):
        data = {
            "title": "API二手相机",
            "category": self.category.id,
            "item_type": Listing.ItemType.PHYSICAL,
            "price": "388.00",
            "condition": Listing.Condition.LIKE_NEW,
            "description": "功能正常。",
            "delivery_notes": "地铁站面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "virtual_valid_until": None,
        }
        data.update(overrides)
        return data

    def create_listing(self, **overrides):
        data = {
            "owner": self.seller,
            "category": self.category,
            "title": "公开商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("99.00"),
            "condition": Listing.Condition.GOOD,
            "description": "公开描述",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def test_categories_returns_only_active_categories(self):
        response = self.api_client.get(reverse("api:catalog_categories"))

        assert response.status_code == 200
        names = [item["name"] for item in response.json()]
        assert "API数码" in names
        assert "API停用分类" not in names

    def test_public_listing_list_filters_active_listings(self):
        match = self.create_listing(title="蓝牙耳机", description="支持降噪")
        self.create_listing(title="普通键盘", description="无关描述")
        self.create_listing(title="草稿商品", status=Listing.Status.DRAFT, published_at=None)
        self.create_listing(title="停用分类商品", category=self.inactive_category)

        response = self.api_client.get(reverse("api:catalog_listings"), {"q": "蓝牙"})

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["results"][0]["id"] == match.id
        assert body["results"][0]["category"]["name"] == "API数码"

    def test_public_detail_hides_inactive_or_non_active_listing(self):
        active = self.create_listing(title="详情商品")
        draft = self.create_listing(
            title="草稿详情",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        ok_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": active.id})
        )
        hidden_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": draft.id})
        )

        assert ok_response.status_code == 200
        assert ok_response.json()["title"] == "详情商品"
        assert hidden_response.status_code == 404

    def test_paid_buyer_and_seller_can_view_reserved_or_sold_detail(self):
        buyer = User.objects.create_user(
            username="detailbuy",
            email="detail_buyer@example.com",
            password="StrongPass123",
        )
        reserved = self.create_listing(
            title="交易中详情",
            status=Listing.Status.RESERVED,
        )
        sold = self.create_listing(
            title="已售详情",
            status=Listing.Status.SOLD,
        )
        Order.objects.create(
            buyer=buyer,
            seller=self.seller,
            listing=reserved,
            buyer_display_name=buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=reserved.title,
            order_price=reserved.price,
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            payment_deadline=timezone.now(),
        )
        Order.objects.create(
            buyer=buyer,
            seller=self.seller,
            listing=sold,
            buyer_display_name=buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=sold.title,
            order_price=sold.price,
            status=Order.OrderStatus.COMPLETED,
            payment_deadline=timezone.now(),
        )

        buyer_reserved_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id}),
            **self.auth_headers(buyer),
        )
        seller_sold_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": sold.id}),
            **self.auth_headers(self.seller),
        )

        assert buyer_reserved_response.status_code == 200
        assert buyer_reserved_response.json()["title"] == "交易中详情"
        assert seller_sold_response.status_code == 200
        assert seller_sold_response.json()["title"] == "已售详情"

    def test_non_participant_cannot_view_reserved_or_sold_detail(self):
        reserved = self.create_listing(
            title="路人不可见",
            status=Listing.Status.RESERVED,
        )

        guest_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id})
        )
        other_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id}),
            **self.auth_headers(self.other_user),
        )

        assert guest_response.status_code == 404
        assert other_response.status_code == 404

    def test_owner_can_view_own_draft_listing_detail(self):
        draft = self.create_listing(
            title="编辑页草稿",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        response = self.api_client.get(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": draft.id}),
            **self.auth_headers(self.seller),
        )

        assert response.status_code == 200
        assert response.json()["id"] == draft.id
        assert response.json()["title"] == "编辑页草稿"
        assert response.json()["status"] == Listing.Status.DRAFT

    def test_non_owner_cannot_view_private_listing_detail(self):
        draft = self.create_listing(
            title="他人草稿",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        response = self.api_client.get(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": draft.id}),
            **self.auth_headers(self.other_user),
        )

        assert response.status_code == 403

    def test_my_listing_list_filters_and_sorts_own_listings(self):
        target = self.create_listing(
            title="我的蓝牙耳机",
            description="轻微使用痕迹",
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
        )
        Listing.objects.filter(pk=target.pk).update(
            updated_at=timezone.now() - timezone.timedelta(days=2)
        )
        wrong_status = self.create_listing(
            title="我的蓝牙草稿",
            status=Listing.Status.DRAFT,
            price=Decimal("80.00"),
            published_at=None,
        )
        too_expensive = self.create_listing(
            title="我的蓝牙音箱",
            status=Listing.Status.ACTIVE,
            price=Decimal("188.00"),
        )
        other_owner = self.create_listing(
            owner=self.other_user,
            title="别人的蓝牙耳机",
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
        )

        response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {
                "q": " 蓝牙 ",
                "status": Listing.Status.ACTIVE,
                "min_price": "50",
                "max_price": "100",
                "updated_after": (timezone.now() - timezone.timedelta(days=3)).isoformat(),
                "updated_before": (timezone.now() - timezone.timedelta(days=1)).isoformat(),
                "sort": "price_asc",
            },
            **self.auth_headers(self.seller),
        )

        ids = [item["id"] for item in response.json()["results"]]
        assert response.status_code == 200
        assert ids == [target.id]
        assert wrong_status.id not in ids
        assert too_expensive.id not in ids
        assert other_owner.id not in ids

    def test_my_listing_list_invalid_filter_and_page_size_cap(self):
        for index in range(55):
            self.create_listing(title=f"我的分页商品{index}")

        invalid_price_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {"min_price": "100", "max_price": "10"},
            **self.auth_headers(self.seller),
        )
        invalid_time_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {
                "updated_after": "2026-05-02T10:00:00+08:00",
                "updated_before": "2026-05-01T10:00:00+08:00",
            },
            **self.auth_headers(self.seller),
        )
        page_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {"page_size": "999"},
            **self.auth_headers(self.seller),
        )
        keyword_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {"q": "商" * 51},
            **self.auth_headers(self.seller),
        )

        assert invalid_price_response.status_code == 400
        assert "最高价格不得低于最低价格" in invalid_price_response.json()["message"]
        assert invalid_time_response.status_code == 400
        assert "更新时间截止不得早于更新时间起始" in invalid_time_response.json()["message"]
        assert keyword_response.status_code == 400
        assert "搜索关键词不能超过50个字符" in keyword_response.json()["message"]
        assert page_response.status_code == 200
        assert page_response.json()["page_size"] == 50
        assert len(page_response.json()["results"]) == 50

    def test_create_update_publish_deactivate_and_reactivate_listing(self):
        create_response = self.api_client.post(
            reverse("api:catalog_my_listings"),
            data=self.listing_payload(),
            format="json",
            **self.auth_headers(self.seller),
        )
        assert create_response.status_code == 201
        listing_id = create_response.json()["id"]
        assert create_response.json()["status"] == Listing.Status.DRAFT

        update_response = self.api_client.patch(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": listing_id}),
            data={"title": "更新后的相机", "price": "399.00"},
            format="json",
            **self.auth_headers(self.seller),
        )
        assert update_response.status_code == 200
        assert update_response.json()["title"] == "更新后的相机"

        publish_response = self.api_client.post(
            reverse("api:catalog_my_listing_publish", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        assert publish_response.status_code == 200
        assert publish_response.json()["status"] == Listing.Status.ACTIVE

        deactivate_response = self.api_client.post(
            reverse("api:catalog_my_listing_deactivate", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        assert deactivate_response.status_code == 200
        assert deactivate_response.json()["status"] == Listing.Status.WITHDRAWN

        reactivate_response = self.api_client.post(
            reverse("api:catalog_my_listing_reactivate", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        assert reactivate_response.status_code == 200
        assert reactivate_response.json()["status"] == Listing.Status.ACTIVE

    def test_non_owner_cannot_mutate_listing(self):
        listing = self.create_listing()

        response = self.api_client.patch(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": listing.id}),
            data={"title": "越权修改"},
            format="json",
            **self.auth_headers(self.other_user),
        )

        assert response.status_code == 403
        listing.refresh_from_db()
        assert listing.title != "越权修改"

    def test_image_upload_reorder_delete_and_limit(self):
        listing = self.create_listing(status=Listing.Status.DRAFT, published_at=None)

        upload_response = self.api_client.post(
            reverse("api:catalog_my_listing_images_upload", kwargs={"pk": listing.id}),
            data={
                "images": [
                    build_png_image("first.png"),
                    build_png_image("second.png"),
                ]
            },
            format="multipart",
            **self.auth_headers(self.seller),
        )
        assert upload_response.status_code == 201
        image_ids = [image["id"] for image in upload_response.json()["images"]]
        assert len(image_ids) == 2

        reorder_response = self.api_client.post(
            reverse("api:catalog_my_listing_images_reorder", kwargs={"pk": listing.id}),
            data={"image_ids": list(reversed(image_ids))},
            format="json",
            **self.auth_headers(self.seller),
        )
        assert reorder_response.status_code == 200
        assert [image["id"] for image in reorder_response.json()["images"]] == list(
            reversed(image_ids)
        )

        delete_response = self.api_client.delete(
            reverse(
                "api:catalog_my_listing_images_delete",
                kwargs={"pk": listing.id, "image_id": image_ids[0]},
            ),
            **self.auth_headers(self.seller),
        )
        assert delete_response.status_code == 204
        assert ListingImage.objects.filter(pk=image_ids[0]).exists() is False

        too_many_response = self.api_client.post(
            reverse("api:catalog_my_listing_images_upload", kwargs={"pk": listing.id}),
            data={"images": [build_png_image(f"extra-{index}.png") for index in range(6)]},
            format="multipart",
            **self.auth_headers(self.seller),
        )
        assert too_many_response.status_code == 400

    def test_invalid_filter_returns_json_error(self):
        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"min_price": "100", "max_price": "10"},
        )

        assert response.status_code == 400
        assert "message" in response.json()
        assert "最高价格不得低于最低价格" in response.json()["message"]

    def test_invalid_published_range_returns_json_error(self):
        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {
                "published_after": "2026-05-02T10:00",
                "published_before": "2026-05-01T10:00",
            },
        )

        assert response.status_code == 400
        assert "发布时间截止不得早于发布时间起始" in response.json()["message"]

    def test_public_listing_list_supports_published_range_filter(self):
        old = self.create_listing(
            title="较早发布",
            published_at=timezone.now() - timezone.timedelta(days=5),
        )
        target = self.create_listing(
            title="区间发布",
            published_at=timezone.now() - timezone.timedelta(days=2),
        )
        new = self.create_listing(title="最新发布", published_at=timezone.now())

        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {
                "published_after": (timezone.now() - timezone.timedelta(days=3)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "published_before": (timezone.now() - timezone.timedelta(days=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            },
        )

        ids = [item["id"] for item in response.json()["results"]]
        assert response.status_code == 200
        assert target.id in ids
        assert old.id not in ids
        assert new.id not in ids

    def test_blank_and_too_long_keyword_handling(self):
        first = self.create_listing(title="蓝牙耳机")
        second = self.create_listing(title="普通键盘")

        blank_response = self.api_client.get(reverse("api:catalog_listings"), {"q": "   "})
        long_response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"q": "蓝" * 51},
        )

        ids = [item["id"] for item in blank_response.json()["results"]]
        assert blank_response.status_code == 200
        assert first.id in ids
        assert second.id in ids
        assert long_response.status_code == 400
        assert "搜索关键词不能超过50个字符" in long_response.json()["message"]

    def test_public_listing_page_size_is_capped_at_50(self):
        for index in range(55):
            self.create_listing(title=f"分页商品{index}")

        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"page_size": "999"},
        )

        body = response.json()
        assert response.status_code == 200
        assert body["page_size"] == 50
        assert len(body["results"]) == 50

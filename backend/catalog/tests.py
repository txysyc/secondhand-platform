from decimal import Decimal
from io import BytesIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.admin import CategoryAdmin, ListingAdmin
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


class CategoryModelTest(TestCase):
    """分类模型基础行为测试。"""

    def test_category_defaults_to_active_and_returns_name(self):
        category = Category.objects.create(name="数码产品")

        self.assertTrue(category.is_active)
        self.assertEqual(str(category), "数码产品")

    def test_category_name_must_be_unique(self):
        Category.objects.create(name="图书")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(name="图书")

    def test_category_can_be_deactivated_without_deletion(self):
        category = Category.objects.create(name="生活用品")

        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])

        category.refresh_from_db()
        self.assertFalse(category.is_active)
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())


class CategorySelectorTest(TestCase):
    """分类读取查询测试。"""

    def test_get_active_categories_returns_only_active_categories_in_stable_order(self):
        first = Category.objects.create(name="数码产品")
        Category.objects.create(name="停用分类", is_active=False)
        second = Category.objects.create(name="生活用品")

        categories = list(get_active_categories())

        self.assertEqual(categories, [first, second])
        self.assertNotIn("停用分类", [category.name for category in categories])


class ListingModelTest(TestCase):
    """商品模型基础行为测试。"""

    def setUp(self):
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

        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.category, self.category)
        self.assertEqual(listing.price, Decimal("199.90"))
        self.assertEqual(str(listing), "二手键盘")

    def test_item_type_supports_physical_and_virtual_with_chinese_labels(self):
        physical = self.create_listing(item_type=Listing.ItemType.PHYSICAL)
        virtual = self.create_listing(
            title="虚拟兑换码",
            item_type=Listing.ItemType.VIRTUAL,
            price=Decimal("29.00"),
        )

        self.assertEqual(physical.get_item_type_display(), "实体商品")
        self.assertEqual(virtual.get_item_type_display(), "虚拟商品")

    def test_listing_status_contains_required_lifecycle_values(self):
        required_values = {"draft", "active", "reserved", "sold", "withdrawn"}

        self.assertTrue(required_values.issubset(set(Listing.Status.values)))

    def test_listing_owner_field_uses_current_custom_user_model(self):
        field = Listing._meta.get_field("owner")

        self.assertIs(field.remote_field.model, get_user_model())

    def test_listing_category_and_item_type_are_independent_fields(self):
        listing = self.create_listing(item_type=Listing.ItemType.VIRTUAL)

        self.assertEqual(listing.category.name, "数码产品")
        self.assertEqual(listing.item_type, "virtual")
        self.assertFalse(Category.objects.filter(name="虚拟商品").exists())

    def test_listing_price_preserves_two_decimal_places(self):
        listing = self.create_listing(price=Decimal("12.30"))

        listing.refresh_from_db()

        self.assertEqual(listing.price, Decimal("12.30"))
        self.assertEqual(abs(listing.price.as_tuple().exponent), 2)

    def test_listing_published_at_defaults_to_none(self):
        listing = self.create_listing()

        self.assertIsNone(listing.published_at)


class CatalogAdminTest(TestCase):
    """catalog 后台注册与配置测试。"""

    def test_category_and_listing_are_registered_to_admin_site(self):
        self.assertIsInstance(admin.site._registry[Category], CategoryAdmin)
        self.assertIsInstance(admin.site._registry[Listing], ListingAdmin)

    def test_category_admin_supports_active_filter_and_name_search(self):
        category_admin = admin.site._registry[Category]

        self.assertEqual(
            list(category_admin.list_display),
            ["name", "is_active", "created_at", "updated_at"],
        )
        self.assertIn("is_active", category_admin.list_filter)
        self.assertIn("name", category_admin.search_fields)

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
            self.assertIn(field, listing_admin.list_display)
        self.assertNotIn("delivery_notes", listing_admin.list_display)

        for field in ["status", "category", "owner", "item_type", "created_at"]:
            self.assertIn(field, listing_admin.list_filter)

        for field in ["title", "description", "owner__username", "category__name"]:
            self.assertIn(field, listing_admin.search_fields)

        self.assertEqual(listing_admin.list_select_related, ["owner", "category"])
        for field in ["created_at", "updated_at", "published_at"]:
            self.assertIn(field, listing_admin.readonly_fields)

    def test_listing_admin_exposes_image_count_and_image_inline(self):
        listing_admin = admin.site._registry[Listing]

        self.assertIn("image_count_value", listing_admin.list_display)
        image_inline = next(
            inline for inline in listing_admin.inlines if inline.model is ListingImage
        )
        self.assertEqual(image_inline.max_num, 6)

    def test_listing_admin_uses_delivery_notes_summary(self):
        listing_admin = admin.site._registry[Listing]
        listing = Listing(delivery_notes="这是一段超过二十个字符的交付说明用于验证摘要")

        self.assertEqual(listing_admin.delivery_notes_summary(listing), listing.delivery_notes[0:20])

    def test_superuser_can_open_category_and_listing_admin_changelists(self):
        superuser = get_user_model().objects.create_superuser(
            username="catadmin",
            email="catalogadmin@example.com",
            password="StrongPass123",
        )
        self.client.force_login(superuser)

        category_response = self.client.get(reverse("admin:catalog_category_changelist"))
        listing_response = self.client.get(reverse("admin:catalog_listing_changelist"))

        self.assertEqual(category_response.status_code, 200)
        self.assertEqual(listing_response.status_code, 200)

    def test_regular_user_cannot_open_listing_admin_changelist(self):
        user = get_user_model().objects.create_user(
            username="catnorm",
            email="catalognormal@example.com",
            password="StrongPass123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:catalog_listing_changelist"))

        self.assertIn(response.status_code, [302, 403])


class PublicListingSelectorTest(TestCase):
    """公开商品列表 selector 测试。"""

    def setUp(self):
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

        self.assertEqual(listings, [active])

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

        self.assertEqual(listings, [active])

    def test_queryset_uses_stable_published_at_and_id_desc_order(self):
        published_at = timezone.now() - timezone.timedelta(days=1)
        older = self.make_listing(
            title="较早商品",
            published_at=published_at - timezone.timedelta(hours=1),
        )
        first_same_time = self.make_listing(title="同时间一号", published_at=published_at)
        second_same_time = self.make_listing(title="同时间二号", published_at=published_at)

        listings = list(get_public_listing_queryset())

        self.assertEqual(listings, [second_same_time, first_same_time, older])

    def test_keyword_matches_title_or_description(self):
        match_title = self.make_listing(title="蓝牙耳机", description="无关描述")
        match_desc = self.make_listing(title="无关标题", description="蓝牙音箱描述")
        no_match = self.make_listing(title="无关标题", description="无关描述")

        results = list(get_public_listing_queryset({"q": "蓝牙"}))

        self.assertIn(match_title, results)
        self.assertIn(match_desc, results)
        self.assertNotIn(no_match, results)

    def test_category_filter(self):
        other_category = Category.objects.create(name="另一分类")
        target = self.make_listing(title="目标分类商品", category=self.category)
        other = self.make_listing(title="其他分类商品", category=other_category)

        results = list(get_public_listing_queryset({"category": self.category}))

        self.assertIn(target, results)
        self.assertNotIn(other, results)

    def test_item_type_filter(self):
        physical = self.make_listing(title="实体", item_type=Listing.ItemType.PHYSICAL)
        virtual = self.make_listing(title="虚拟", item_type=Listing.ItemType.VIRTUAL)

        results = list(get_public_listing_queryset({"item_type": "virtual"}))

        self.assertNotIn(physical, results)
        self.assertIn(virtual, results)

    def test_price_range_filter(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        mid = self.make_listing(title="中等", price=Decimal("50.00"))
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))

        results = list(
            get_public_listing_queryset({"min_price": Decimal("20"), "max_price": Decimal("100")})
        )

        self.assertNotIn(cheap, results)
        self.assertIn(mid, results)
        self.assertNotIn(expensive, results)

    def test_min_price_filter_can_work_alone(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        mid = self.make_listing(title="中等", price=Decimal("50.00"))

        results = list(get_public_listing_queryset({"min_price": Decimal("20")}))

        self.assertNotIn(cheap, results)
        self.assertIn(mid, results)

    def test_max_price_filter_can_work_alone(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        mid = self.make_listing(title="中等", price=Decimal("50.00"))

        results = list(get_public_listing_queryset({"max_price": Decimal("20")}))

        self.assertIn(cheap, results)
        self.assertNotIn(mid, results)

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

        self.assertIn(reserved, listings)
        self.assertIn(sold, listings)

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

        self.assertNotIn(reserved, listings)

    def test_sort_price_asc(self):
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))

        results = list(get_public_listing_queryset({"sort": "price_asc"}))

        self.assertEqual(results, [cheap, expensive])

    def test_sort_price_desc(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))

        results = list(get_public_listing_queryset({"sort": "price_desc"}))

        self.assertEqual(results, [expensive, cheap])

    def test_sort_oldest(self):
        older = self.make_listing(
            title="旧", published_at=timezone.now() - timezone.timedelta(days=2)
        )
        newer = self.make_listing(
            title="新", published_at=timezone.now() - timezone.timedelta(days=1)
        )

        results = list(get_public_listing_queryset({"sort": "oldest"}))

        self.assertEqual(results, [older, newer])

    def test_unknown_sort_falls_back_to_default(self):
        older = self.make_listing(
            title="旧",
            published_at=timezone.now() - timezone.timedelta(days=2),
        )
        newer = self.make_listing(
            title="新",
            published_at=timezone.now() - timezone.timedelta(days=1),
        )

        results = list(get_public_listing_queryset({"sort": "invalid_sort"}))

        self.assertEqual(results, [newer, older])

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

        results = list(
            get_public_listing_queryset({
                "q": "蓝牙",
                "item_type": "physical",
                "min_price": Decimal("10"),
                "max_price": Decimal("100"),
            })
        )

        self.assertEqual(results, [target])


class ChangeListingStatusServiceTest(TestCase):
    """商品状态变更服务测试。"""

    def setUp(self):
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

        self.assertEqual(result.status, Listing.Status.WITHDRAWN)
        self.assertGreater(result.updated_at, baseline_updated_at)
        self.assertEqual(result.owner_id, self.user.id)
        self.assertIsNotNone(result.published_at)

    def test_withdraw_rejects_non_active_statuses(self):
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]:
            listing = self.make_listing(status=status)

            with self.assertRaises(ValidationError):
                change_listing_status(self.user, listing, ACTION_WITHDRAW)

            listing.refresh_from_db()
            self.assertEqual(listing.status, status)

    def test_restore_active_keeps_published_at_and_returns_to_active(self):
        published_at = timezone.now() - timezone.timedelta(days=5)
        listing = self.make_listing(
            status=Listing.Status.WITHDRAWN, published_at=published_at
        )

        result = change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)
        result.refresh_from_db()

        self.assertEqual(result.status, Listing.Status.ACTIVE)
        self.assertEqual(result.published_at, published_at)

    def test_restore_active_back_fills_missing_published_at(self):
        listing = self.make_listing(
            status=Listing.Status.WITHDRAWN, published_at=None
        )

        before = timezone.now()
        result = change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)
        result.refresh_from_db()

        self.assertEqual(result.status, Listing.Status.ACTIVE)
        self.assertIsNotNone(result.published_at)
        self.assertGreaterEqual(
            result.published_at, before - timezone.timedelta(seconds=1)
        )

    def test_restore_active_blocked_when_category_disabled(self):
        listing = self.make_listing(status=Listing.Status.WITHDRAWN)
        self.category.is_active = False
        self.category.save(update_fields=["is_active", "updated_at"])

        with self.assertRaises(ValidationError):
            change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)

        listing.refresh_from_db()
        self.assertEqual(listing.status, Listing.Status.WITHDRAWN)

    def test_restore_active_rejects_non_withdrawn_statuses(self):
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.ACTIVE,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
        ]:
            listing = self.make_listing(status=status)

            with self.assertRaises(ValidationError):
                change_listing_status(self.user, listing, ACTION_RESTORE_ACTIVE)

            listing.refresh_from_db()
            self.assertEqual(listing.status, status)

    def test_unknown_action_raises_validation_error(self):
        listing = self.make_listing(status=Listing.Status.ACTIVE)

        with self.assertRaises(ValidationError):
            change_listing_status(self.user, listing, "mark_sold")
        with self.assertRaises(ValidationError):
            change_listing_status(self.user, listing, "")

        listing.refresh_from_db()
        self.assertEqual(listing.status, Listing.Status.ACTIVE)

    def test_non_owner_cannot_change_status(self):
        listing = self.make_listing(status=Listing.Status.ACTIVE)

        with self.assertRaises(PermissionDenied):
            change_listing_status(self.other_user, listing, ACTION_WITHDRAW)

        listing.refresh_from_db()
        self.assertEqual(listing.status, Listing.Status.ACTIVE)




def build_png_image(name="listing.png", size=(16, 16)):
    """构造测试用 PNG 图片。"""

    buffer = BytesIO()
    image = Image.new("RGB", size, color="white")
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.InMemoryStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class CatalogApiTests(APITestCase):
    """P3 商品 API 测试。"""

    def setUp(self):
        self.client = APIClient()
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

    def auth_headers(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

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
        response = self.client.get(reverse("api:catalog_categories"))

        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertIn("API数码", names)
        self.assertNotIn("API停用分类", names)

    def test_public_listing_list_filters_active_listings(self):
        match = self.create_listing(title="蓝牙耳机", description="支持降噪")
        self.create_listing(title="普通键盘", description="无关描述")
        self.create_listing(title="草稿商品", status=Listing.Status.DRAFT, published_at=None)
        self.create_listing(title="停用分类商品", category=self.inactive_category)

        response = self.client.get(reverse("api:catalog_listings"), {"q": "蓝牙"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], match.id)
        self.assertEqual(body["results"][0]["category"]["name"], "API数码")

    def test_public_detail_hides_inactive_or_non_active_listing(self):
        active = self.create_listing(title="详情商品")
        draft = self.create_listing(
            title="草稿详情",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        ok_response = self.client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": active.id})
        )
        hidden_response = self.client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": draft.id})
        )

        self.assertEqual(ok_response.status_code, 200)
        self.assertEqual(ok_response.json()["title"], "详情商品")
        self.assertEqual(hidden_response.status_code, 404)

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

        buyer_reserved_response = self.client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id}),
            **self.auth_headers(buyer),
        )
        seller_sold_response = self.client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": sold.id}),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(buyer_reserved_response.status_code, 200)
        self.assertEqual(buyer_reserved_response.json()["title"], "交易中详情")
        self.assertEqual(seller_sold_response.status_code, 200)
        self.assertEqual(seller_sold_response.json()["title"], "已售详情")

    def test_non_participant_cannot_view_reserved_or_sold_detail(self):
        reserved = self.create_listing(
            title="路人不可见",
            status=Listing.Status.RESERVED,
        )

        guest_response = self.client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id})
        )
        other_response = self.client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id}),
            **self.auth_headers(self.other_user),
        )

        self.assertEqual(guest_response.status_code, 404)
        self.assertEqual(other_response.status_code, 404)

    def test_owner_can_view_own_draft_listing_detail(self):
        draft = self.create_listing(
            title="编辑页草稿",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        response = self.client.get(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": draft.id}),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], draft.id)
        self.assertEqual(response.json()["title"], "编辑页草稿")
        self.assertEqual(response.json()["status"], Listing.Status.DRAFT)

    def test_non_owner_cannot_view_private_listing_detail(self):
        draft = self.create_listing(
            title="他人草稿",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        response = self.client.get(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": draft.id}),
            **self.auth_headers(self.other_user),
        )

        self.assertEqual(response.status_code, 403)

    def test_create_update_publish_deactivate_and_reactivate_listing(self):
        create_response = self.client.post(
            reverse("api:catalog_my_listings"),
            data=self.listing_payload(),
            format="json",
            **self.auth_headers(self.seller),
        )
        self.assertEqual(create_response.status_code, 201)
        listing_id = create_response.json()["id"]
        self.assertEqual(create_response.json()["status"], Listing.Status.DRAFT)

        update_response = self.client.patch(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": listing_id}),
            data={"title": "更新后的相机", "price": "399.00"},
            format="json",
            **self.auth_headers(self.seller),
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["title"], "更新后的相机")

        publish_response = self.client.post(
            reverse("api:catalog_my_listing_publish", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["status"], Listing.Status.ACTIVE)

        deactivate_response = self.client.post(
            reverse("api:catalog_my_listing_deactivate", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        self.assertEqual(deactivate_response.status_code, 200)
        self.assertEqual(deactivate_response.json()["status"], Listing.Status.WITHDRAWN)

        reactivate_response = self.client.post(
            reverse("api:catalog_my_listing_reactivate", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        self.assertEqual(reactivate_response.status_code, 200)
        self.assertEqual(reactivate_response.json()["status"], Listing.Status.ACTIVE)

    def test_non_owner_cannot_mutate_listing(self):
        listing = self.create_listing()

        response = self.client.patch(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": listing.id}),
            data={"title": "越权修改"},
            format="json",
            **self.auth_headers(self.other_user),
        )

        self.assertEqual(response.status_code, 403)
        listing.refresh_from_db()
        self.assertNotEqual(listing.title, "越权修改")

    def test_image_upload_reorder_delete_and_limit(self):
        listing = self.create_listing(status=Listing.Status.DRAFT, published_at=None)

        upload_response = self.client.post(
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
        self.assertEqual(upload_response.status_code, 201)
        image_ids = [image["id"] for image in upload_response.json()["images"]]
        self.assertEqual(len(image_ids), 2)

        reorder_response = self.client.post(
            reverse("api:catalog_my_listing_images_reorder", kwargs={"pk": listing.id}),
            data={"image_ids": list(reversed(image_ids))},
            format="json",
            **self.auth_headers(self.seller),
        )
        self.assertEqual(reorder_response.status_code, 200)
        self.assertEqual(
            [image["id"] for image in reorder_response.json()["images"]],
            list(reversed(image_ids)),
        )

        delete_response = self.client.delete(
            reverse(
                "api:catalog_my_listing_images_delete",
                kwargs={"pk": listing.id, "image_id": image_ids[0]},
            ),
            **self.auth_headers(self.seller),
        )
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(ListingImage.objects.filter(pk=image_ids[0]).exists())

        too_many_response = self.client.post(
            reverse("api:catalog_my_listing_images_upload", kwargs={"pk": listing.id}),
            data={"images": [build_png_image(f"extra-{index}.png") for index in range(6)]},
            format="multipart",
            **self.auth_headers(self.seller),
        )
        self.assertEqual(too_many_response.status_code, 400)

    def test_invalid_filter_returns_json_error(self):
        response = self.client.get(
            reverse("api:catalog_listings"),
            {"min_price": "100", "max_price": "10"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.json())

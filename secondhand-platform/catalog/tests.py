from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.admin import CategoryAdmin, ListingAdmin
from catalog.models import Category, Listing
from catalog.selectors import get_active_categories


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
            "created_at",
            "updated_at",
        ]:
            self.assertIn(field, listing_admin.list_display)

        for field in ["category", "item_type", "status", "created_at"]:
            self.assertIn(field, listing_admin.list_filter)

        for field in ["title", "description", "owner__username"]:
            self.assertIn(field, listing_admin.search_fields)

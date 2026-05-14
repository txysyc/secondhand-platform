from decimal import Decimal
import shutil
import tempfile
from io import BytesIO

from django.contrib import admin
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from catalog.admin import CategoryAdmin, ListingAdmin
from catalog.forms import ListingDraftForm, ListingImageFormSet
from catalog.models import Category, Listing, ListingImage
from catalog.selectors import get_active_categories
from catalog.services import create_listing_draft


TEMP_MEDIA_ROOT = tempfile.mkdtemp()


def create_test_image(name="test.png", size=(16, 16), image_format="PNG"):
    image_file = BytesIO()
    image = Image.new("RGB", size, color="white")
    image.save(image_file, image_format)
    content_type = f"image/{image_format.lower()}"
    return SimpleUploadedFile(name, image_file.getvalue(), content_type=content_type)


def create_invalid_upload(name="bad.txt"):
    return SimpleUploadedFile(name, b"not-an-image", content_type="text/plain")


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

    def test_listing_admin_exposes_image_count(self):
        listing_admin = admin.site._registry[Listing]

        self.assertIn("image_count_value", listing_admin.list_display)


class ListingDraftFormTest(TestCase):
    """商品草稿表单校验测试。"""

    def setUp(self):
        self.active_category = Category.objects.create(name="数码产品")
        self.inactive_category = Category.objects.create(name="停用分类", is_active=False)

    def valid_form_data(self, **overrides):
        data = {
            "title": "二手显示器",
            "category": str(self.active_category.pk),
            "item_type": Listing.ItemType.PHYSICAL,
            "price": "300.00",
            "condition": Listing.Condition.GOOD,
            "description": "正常使用。",
            "delivery_notes": "工作日晚上面交。",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "virtual_valid_until": "",
        }
        data.update(overrides)
        return data

    def test_category_queryset_only_contains_active_categories(self):
        form = ListingDraftForm()

        self.assertIn(self.active_category, form.fields["category"].queryset)
        self.assertNotIn(self.inactive_category, form.fields["category"].queryset)

    def test_inactive_category_submission_is_rejected(self):
        form = ListingDraftForm(
            data=self.valid_form_data(category=str(self.inactive_category.pk))
        )

        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_physical_listing_requires_condition_and_delivery_method(self):
        form = ListingDraftForm(
            data=self.valid_form_data(condition="", physical_delivery_method="")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("实体商品必须填写成色", form.errors["condition"])
        self.assertIn("实体商品必须选择交付方式", form.errors["physical_delivery_method"])

    def test_virtual_listing_requires_valid_until_and_clears_physical_fields(self):
        future_date = timezone.localdate() + timezone.timedelta(days=7)
        form = ListingDraftForm(
            data=self.valid_form_data(
                item_type=Listing.ItemType.VIRTUAL,
                virtual_valid_until=future_date.isoformat(),
                condition=Listing.Condition.GOOD,
                physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
            )
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["condition"])
        self.assertIsNone(form.cleaned_data["physical_delivery_method"])

    def test_virtual_listing_rejects_missing_or_past_valid_until(self):
        missing_form = ListingDraftForm(
            data=self.valid_form_data(item_type=Listing.ItemType.VIRTUAL)
        )
        past_form = ListingDraftForm(
            data=self.valid_form_data(
                item_type=Listing.ItemType.VIRTUAL,
                virtual_valid_until=(timezone.localdate() - timezone.timedelta(days=1)).isoformat(),
            )
        )

        self.assertFalse(missing_form.is_valid())
        self.assertIn("虚拟商品需要填写有效期", missing_form.errors["virtual_valid_until"])
        self.assertFalse(past_form.is_valid())
        self.assertIn("有效期不能早于当前日期", past_form.errors["virtual_valid_until"])

    def test_price_must_be_positive(self):
        form = ListingDraftForm(data=self.valid_form_data(price="-1.00"))

        self.assertFalse(form.is_valid())
        self.assertIn("价格必须大于0", form.errors["price"])


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ListingDraftServiceTest(TestCase):
    """商品草稿创建服务测试。"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="seller2",
            email="seller2@example.com",
            password="StrongPass123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other",
            email="other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="图书")

    def valid_form_data(self, **overrides):
        data = {
            "title": "二手教材",
            "category": str(self.category.pk),
            "item_type": Listing.ItemType.PHYSICAL,
            "price": "45.00",
            "condition": Listing.Condition.LIKE_NEW,
            "description": "课程教材。",
            "delivery_notes": "校门口自取。",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "virtual_valid_until": "",
            "owner": str(self.other_user.pk),
            "status": Listing.Status.ACTIVE,
        }
        data.update(overrides)
        return data

    def formset_post_data(self, total_forms):
        return {
            "images-TOTAL_FORMS": str(total_forms),
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "6",
        }

    def test_create_physical_draft_sets_owner_status_and_sort_order(self):
        form = ListingDraftForm(data=self.valid_form_data())
        formset = ListingImageFormSet(
            self.formset_post_data(2),
            {
                "images-0-image": create_test_image("first.png"),
                "images-1-image": create_test_image("second.png"),
            },
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        listing = create_listing_draft(self.user, form, formset)

        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.DRAFT)
        self.assertEqual(listing.item_type, Listing.ItemType.PHYSICAL)
        self.assertIsNone(listing.virtual_valid_until)
        self.assertEqual(list(listing.images.values_list("sort_order", flat=True)), [0, 1])

    def test_create_virtual_draft_clears_physical_fields_and_keeps_category(self):
        future_date = timezone.localdate() + timezone.timedelta(days=3)
        form = ListingDraftForm(
            data=self.valid_form_data(
                item_type=Listing.ItemType.VIRTUAL,
                virtual_valid_until=future_date.isoformat(),
            )
        )
        formset = ListingImageFormSet(self.formset_post_data(0), prefix="images")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        listing = create_listing_draft(self.user, form, formset)

        self.assertEqual(listing.item_type, Listing.ItemType.VIRTUAL)
        self.assertIsNone(listing.condition)
        self.assertIsNone(listing.physical_delivery_method)
        self.assertEqual(listing.category, self.category)
        self.assertFalse(Category.objects.filter(name="虚拟商品").exists())

    def test_invalid_image_count_or_file_does_not_create_listing(self):
        too_many_files = {
            f"images-{index}-image": create_test_image(f"{index}.png")
            for index in range(7)
        }
        form = ListingDraftForm(data=self.valid_form_data())
        formset = ListingImageFormSet(
            self.formset_post_data(7), too_many_files, prefix="images"
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(formset.is_valid())
        self.assertEqual(Listing.objects.count(), 0)

    def test_invalid_image_file_is_rejected_before_listing_is_created(self):
        form = ListingDraftForm(data=self.valid_form_data())
        formset = ListingImageFormSet(
            self.formset_post_data(1),
            {"images-0-image": create_invalid_upload()},
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(formset.is_valid())
        self.assertEqual(Listing.objects.count(), 0)

    def test_oversized_image_file_is_rejected_before_listing_is_created(self):
        oversized = SimpleUploadedFile(
            "oversized.png", b"x" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )
        form = ListingDraftForm(data=self.valid_form_data())
        formset = ListingImageFormSet(
            self.formset_post_data(1),
            {"images-0-image": oversized},
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(formset.is_valid())
        self.assertEqual(Listing.objects.count(), 0)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ListingCreateViewTest(TestCase):
    """商品草稿创建视图测试。"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="seller3",
            email="seller3@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="生活用品")
        self.url = reverse("catalog:listing_create")

    def valid_post_data(self, **overrides):
        data = {
            "title": "闲置台灯",
            "category": str(self.category.pk),
            "item_type": Listing.ItemType.PHYSICAL,
            "price": "25.00",
            "condition": Listing.Condition.FAIR,
            "description": "可以正常使用。",
            "delivery_notes": "宿舍楼下交易。",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.BOTH,
            "virtual_valid_until": "",
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "6",
        }
        data.update(overrides)
        return data

    def test_guest_is_redirected_to_login_with_next(self):
        response = self.client.get(self.url)

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.url}")

    def test_authenticated_user_can_open_create_page(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/listing_form.html")
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "保存草稿")

    def test_valid_post_creates_draft_redirects_and_adds_message(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url, self.valid_post_data())

        self.assertRedirects(response, reverse("users:profile"))
        listing = Listing.objects.get()
        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.DRAFT)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("草稿保存成功", messages)

    def test_valid_post_with_images_creates_ordered_listing_images(self):
        self.client.force_login(self.user)
        data = self.valid_post_data(**{"images-TOTAL_FORMS": "2"})
        data["images-0-image"] = create_test_image("first.png")
        data["images-1-image"] = create_test_image("second.png")

        response = self.client.post(self.url, data=data)

        self.assertRedirects(response, reverse("users:profile"))
        listing = Listing.objects.get()
        self.assertEqual(list(listing.images.values_list("sort_order", flat=True)), [0, 1])

    def test_invalid_post_shows_error_and_does_not_create_listing(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.url, self.valid_post_data(condition="", physical_delivery_method="")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "实体商品必须填写成色")
        self.assertContains(response, "实体商品必须选择交付方式")
        self.assertEqual(Listing.objects.count(), 0)

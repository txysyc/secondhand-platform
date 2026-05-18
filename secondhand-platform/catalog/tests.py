from decimal import Decimal
import shutil
import tempfile
from io import BytesIO

from django.contrib import admin
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from catalog.admin import CategoryAdmin, ListingAdmin
from catalog.forms import ListingFilterForm, ListingForm, ListingImageFormSet
from catalog.models import Category, Listing, ListingImage
from catalog.selectors import (
    get_active_categories,
    get_owner_listing_groups,
    get_publish_listing_queryset,
)
from catalog.services import (
    ACTION_RESTORE_ACTIVE,
    ACTION_WITHDRAW,
    change_listing_status,
    create_listing,
    delete_listing,
    publish_listing,
    update_listing,
)


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
        ]:
            self.assertIn(field, listing_admin.list_display)

        for field in ["category", "item_type", "status", "created_at"]:
            self.assertIn(field, listing_admin.list_filter)

        for field in ["title", "description", "owner__username"]:
            self.assertIn(field, listing_admin.search_fields)

    def test_listing_admin_exposes_image_count(self):
        listing_admin = admin.site._registry[Listing]

        self.assertIn("image_count_value", listing_admin.list_display)


class ListingFormTest(TestCase):
    """商品字段表单校验测试。"""

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
        form = ListingForm()

        self.assertIn(self.active_category, form.fields["category"].queryset)
        self.assertNotIn(self.inactive_category, form.fields["category"].queryset)

    def test_inactive_category_submission_is_rejected(self):
        form = ListingForm(
            data=self.valid_form_data(category=str(self.inactive_category.pk))
        )

        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_physical_listing_requires_condition_and_delivery_method(self):
        form = ListingForm(
            data=self.valid_form_data(condition="", physical_delivery_method="")
        )

        self.assertFalse(form.is_valid())
        self.assertIn("实体商品必须填写成色", form.errors["condition"])
        self.assertIn("实体商品必须选择交付方式", form.errors["physical_delivery_method"])

    def test_virtual_listing_requires_valid_until_and_clears_physical_fields(self):
        future_date = timezone.localdate() + timezone.timedelta(days=7)
        form = ListingForm(
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
        missing_form = ListingForm(
            data=self.valid_form_data(item_type=Listing.ItemType.VIRTUAL)
        )
        past_form = ListingForm(
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
        form = ListingForm(data=self.valid_form_data(price="-1.00"))

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
        form = ListingForm(data=self.valid_form_data())
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

        listing = create_listing(self.user, form, formset, "save_draft")

        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.DRAFT)
        self.assertEqual(listing.item_type, Listing.ItemType.PHYSICAL)
        self.assertIsNone(listing.virtual_valid_until)
        self.assertEqual(list(listing.images.values_list("sort_order", flat=True)), [0, 1])

    def test_create_publish_sets_active_status_published_at_and_owner(self):
        form = ListingForm(data=self.valid_form_data())
        formset = ListingImageFormSet(self.formset_post_data(0), prefix="images")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        listing = create_listing(self.user, form, formset, "publish")

        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertIsNotNone(listing.published_at)

    def test_create_virtual_draft_clears_physical_fields_and_keeps_category(self):
        future_date = timezone.localdate() + timezone.timedelta(days=3)
        form = ListingForm(
            data=self.valid_form_data(
                item_type=Listing.ItemType.VIRTUAL,
                virtual_valid_until=future_date.isoformat(),
            )
        )
        formset = ListingImageFormSet(self.formset_post_data(0), prefix="images")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        listing = create_listing(self.user, form, formset, "save_draft")

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
        form = ListingForm(data=self.valid_form_data())
        formset = ListingImageFormSet(
            self.formset_post_data(7), too_many_files, prefix="images"
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(formset.is_valid())
        self.assertEqual(Listing.objects.count(), 0)

    def test_invalid_image_file_is_rejected_before_listing_is_created(self):
        form = ListingForm(data=self.valid_form_data())
        formset = ListingImageFormSet(
            self.formset_post_data(1),
            {"images-0-image": create_invalid_upload()},
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(formset.is_valid())
        self.assertEqual(Listing.objects.count(), 0)

    def test_invalid_create_intent_is_rejected(self):
        form = ListingForm(data=self.valid_form_data())
        formset = ListingImageFormSet(self.formset_post_data(0), prefix="images")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        with self.assertRaises(ValidationError):
            create_listing(self.user, form, formset, "bad_intent")

    def test_oversized_image_file_is_rejected_before_listing_is_created(self):
        oversized = SimpleUploadedFile(
            "oversized.png", b"x" * (5 * 1024 * 1024 + 1), content_type="image/png"
        )
        form = ListingForm(data=self.valid_form_data())
        formset = ListingImageFormSet(
            self.formset_post_data(1),
            {"images-0-image": oversized},
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(formset.is_valid())
        self.assertEqual(Listing.objects.count(), 0)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ListingUpdateServiceTest(TestCase):
    """商品更新服务测试。"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="seller4",
            email="seller4@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="文具")
        self.listing = Listing.objects.create(
            owner=self.user,
            category=self.category,
            title="旧书",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.DRAFT,
            price=Decimal("20.00"),
            condition=Listing.Condition.GOOD,
            description="旧描述",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
        )

    def valid_form_data(self, **overrides):
        data = {
            "title": "更新后的旧书",
            "category": str(self.category.pk),
            "item_type": Listing.ItemType.PHYSICAL,
            "price": "21.00",
            "condition": Listing.Condition.GOOD,
            "description": "更新后的描述",
            "delivery_notes": "校门口面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "virtual_valid_until": "",
        }
        data.update(overrides)
        return data

    def create_images(self, count):
        return [
            ListingImage.objects.create(
                listing=self.listing,
                image=create_test_image(f"existing-{index}.png"),
                sort_order=index,
            )
            for index in range(count)
        ]

    def formset_post_data(self, images, total_forms, deleted_indexes=None):
        deleted_indexes = deleted_indexes or set()
        data = {
            "images-TOTAL_FORMS": str(total_forms),
            "images-INITIAL_FORMS": str(len(images)),
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "6",
        }
        for index, image in enumerate(images):
            data[f"images-{index}-id"] = str(image.pk)
            if index in deleted_indexes:
                data[f"images-{index}-DELETE"] = "on"
        return data

    def test_formset_counts_final_images_after_deleting_existing_and_adding_new(self):
        images = self.create_images(4)
        data = self.formset_post_data(images, total_forms=7, deleted_indexes={1})
        files = {
            "images-4-image": create_test_image("new-4.png"),
            "images-5-image": create_test_image("new-5.png"),
            "images-6-image": create_test_image("new-6.png"),
        }
        formset = ListingImageFormSet(data, files, instance=self.listing, prefix="images")

        self.assertTrue(formset.is_valid(), formset.errors)

    def test_formset_rejects_more_than_six_final_images(self):
        images = self.create_images(4)
        data = self.formset_post_data(images, total_forms=7)
        files = {
            "images-4-image": create_test_image("new-4.png"),
            "images-5-image": create_test_image("new-5.png"),
            "images-6-image": create_test_image("new-6.png"),
        }
        formset = ListingImageFormSet(data, files, instance=self.listing, prefix="images")

        self.assertFalse(formset.is_valid())

    def test_publish_draft_sets_active_status_published_at_and_keeps_owner(self):
        form = ListingForm(data=self.valid_form_data(), instance=self.listing)
        formset = ListingImageFormSet(
            self.formset_post_data([], total_forms=0),
            instance=self.listing,
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        listing = update_listing(self.user, self.listing, form, formset, "publish")

        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertIsNotNone(listing.published_at)

    def test_publish_listing_rejects_non_draft_listing(self):
        self.listing.status = Listing.Status.ACTIVE
        self.listing.published_at = timezone.now()

        with self.assertRaises(ValidationError):
            publish_listing(self.user, self.listing)

    def test_non_owner_cannot_update_listing(self):
        other_user = get_user_model().objects.create_user(
            username="other4",
            email="other4@example.com",
            password="StrongPass123",
        )
        form = ListingForm(data=self.valid_form_data(), instance=self.listing)
        formset = ListingImageFormSet(
            self.formset_post_data([], total_forms=0),
            instance=self.listing,
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        with self.assertRaises(PermissionDenied):
            update_listing(other_user, self.listing, form, formset, "save_draft")

    def test_active_listing_save_changes_keeps_status_owner_and_published_at(self):
        published_at = timezone.now() - timezone.timedelta(days=2)
        self.listing.status = Listing.Status.ACTIVE
        self.listing.published_at = published_at
        self.listing.save(update_fields=["status", "published_at"])
        form = ListingForm(
            data=self.valid_form_data(
                title="已发布商品新标题",
                owner="999",
                status=Listing.Status.DRAFT,
                published_at="1999-01-01T00:00:00Z",
            ),
            instance=self.listing,
        )
        formset = ListingImageFormSet(
            self.formset_post_data([], total_forms=0),
            instance=self.listing,
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        listing = update_listing(self.user, self.listing, form, formset, "save_changes")
        listing.refresh_from_db()

        self.assertEqual(listing.title, "已发布商品新标题")
        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertEqual(listing.published_at, published_at)

    def test_active_listing_rejects_save_draft_and_publish_intents(self):
        self.listing.status = Listing.Status.ACTIVE
        self.listing.published_at = timezone.now()
        self.listing.save(update_fields=["status", "published_at"])

        for intent in ["save_draft", "publish"]:
            form = ListingForm(data=self.valid_form_data(), instance=self.listing)
            formset = ListingImageFormSet(
                self.formset_post_data([], total_forms=0),
                instance=self.listing,
                prefix="images",
            )

            self.assertTrue(form.is_valid(), form.errors)
            self.assertTrue(formset.is_valid(), formset.errors)

            with self.assertRaises(ValidationError):
                update_listing(self.user, self.listing, form, formset, intent)

    def test_update_deletes_existing_image_adds_new_images_and_reorders(self):
        images = self.create_images(4)
        deleted_file = images[1].image
        deleted_file_name = deleted_file.name
        form = ListingForm(data=self.valid_form_data(), instance=self.listing)
        data = self.formset_post_data(images, total_forms=7, deleted_indexes={1})
        files = {
            "images-4-image": create_test_image("new-4.png"),
            "images-5-image": create_test_image("new-5.png"),
            "images-6-image": create_test_image("new-6.png"),
        }
        formset = ListingImageFormSet(data, files, instance=self.listing, prefix="images")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        with self.captureOnCommitCallbacks(execute=True):
            update_listing(self.user, self.listing, form, formset, "save_draft")

        self.assertEqual(self.listing.images.count(), 6)
        self.assertEqual(
            list(self.listing.images.values_list("sort_order", flat=True)),
            [0, 1, 2, 3, 4, 5],
        )
        self.assertFalse(deleted_file.storage.exists(deleted_file_name))

    def test_update_rejects_invalid_intent(self):
        images = self.create_images(1)
        form = ListingForm(data=self.valid_form_data(), instance=self.listing)
        formset = ListingImageFormSet(
            self.formset_post_data(images, total_forms=1),
            instance=self.listing,
            prefix="images",
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)

        with self.assertRaises(ValidationError):
            update_listing(self.user, self.listing, form, formset, "bad_intent")

    def test_delete_listing_removes_image_files_after_commit(self):
        images = self.create_images(2)
        file_fields = [image.image for image in images]
        file_names = [file_field.name for file_field in file_fields]

        with self.captureOnCommitCallbacks(execute=True):
            delete_listing(self.user, self.listing)

        self.assertFalse(Listing.objects.filter(pk=self.listing.pk).exists())
        for file_field, file_name in zip(file_fields, file_names):
            self.assertFalse(file_field.storage.exists(file_name))

    def test_delete_listing_rejects_reserved_and_sold_statuses(self):
        for status in [Listing.Status.RESERVED, Listing.Status.SOLD]:
            self.listing.status = status
            self.listing.save(update_fields=["status"])

            with self.assertRaises(ValidationError):
                delete_listing(self.user, self.listing)

            self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())


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
            "intent": "save_draft",
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

        listing = Listing.objects.get()
        self.assertRedirects(
            response, reverse("catalog:listing_edit", kwargs={"pk": listing.pk})
        )
        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.DRAFT)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("草稿保存成功", messages)

    def test_valid_publish_post_creates_active_listing(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url, self.valid_post_data(intent="publish"))

        listing = Listing.objects.get()
        self.assertRedirects(
            response, reverse("catalog:listing_edit", kwargs={"pk": listing.pk})
        )
        self.assertEqual(listing.owner, self.user)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertIsNotNone(listing.published_at)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        self.assertIn("商品已发布", messages)

    def test_invalid_intent_post_shows_error_and_does_not_create_listing(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url, self.valid_post_data(intent="bad_intent"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "无效的提交操作")
        self.assertEqual(Listing.objects.count(), 0)

    def test_valid_post_with_images_creates_ordered_listing_images(self):
        self.client.force_login(self.user)
        data = self.valid_post_data(**{"images-TOTAL_FORMS": "2"})
        data["images-0-image"] = create_test_image("first.png")
        data["images-1-image"] = create_test_image("second.png")

        response = self.client.post(self.url, data=data)

        listing = Listing.objects.get()
        self.assertRedirects(
            response, reverse("catalog:listing_edit", kwargs={"pk": listing.pk})
        )
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


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ListingUpdateViewTest(TestCase):
    """商品编辑视图测试。"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="seller5",
            email="seller5@example.com",
            password="StrongPass123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other5",
            email="other5@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="家具")
        self.listing = Listing.objects.create(
            owner=self.user,
            category=self.category,
            title="旧椅子",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.DRAFT,
            price=Decimal("35.00"),
            condition=Listing.Condition.FAIR,
            description="可正常使用。",
            delivery_notes="自提",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
        )

    def url(self, listing=None):
        listing = listing or self.listing
        return reverse("catalog:listing_edit", kwargs={"pk": listing.pk})

    def valid_post_data(self, **overrides):
        data = {
            "title": "更新后的旧椅子",
            "category": str(self.category.pk),
            "item_type": Listing.ItemType.PHYSICAL,
            "price": "40.00",
            "condition": Listing.Condition.GOOD,
            "description": "更新后的描述。",
            "delivery_notes": "校门口自提",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "virtual_valid_until": "",
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "6",
            "intent": "save_draft",
        }
        data.update(overrides)
        return data

    def test_guest_is_redirected_to_login_with_next(self):
        response = self.client.get(self.url())

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.url()}")

    def test_owner_can_open_edit_page_with_bound_formset(self):
        ListingImage.objects.create(
            listing=self.listing,
            image=create_test_image("existing.png"),
            sort_order=0,
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/listing_form.html")
        self.assertContains(response, "更新后的旧椅子", count=0)
        self.assertContains(response, self.listing.title)
        self.assertContains(response, "删除这张图片")
        self.assertContains(response, "发布商品")

    def test_non_owner_get_returns_403(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 403)

    def test_non_owner_post_returns_403_and_does_not_change_listing(self):
        self.client.force_login(self.other_user)

        response = self.client.post(self.url(), self.valid_post_data())

        self.assertEqual(response.status_code, 403)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "旧椅子")

    def test_update_draft_with_save_draft_changes_editable_fields(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url(), self.valid_post_data())

        self.assertRedirects(response, self.url())
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "更新后的旧椅子")
        self.assertEqual(self.listing.status, Listing.Status.DRAFT)
        self.assertIsNone(self.listing.published_at)

    def test_update_draft_with_publish_sets_active_and_published_at(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url(), self.valid_post_data(intent="publish"))

        self.assertRedirects(response, self.url())
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)
        self.assertIsNotNone(self.listing.published_at)
        self.assertEqual(self.listing.owner, self.user)

    def test_get_does_not_publish_listing(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.DRAFT)
        self.assertIsNone(self.listing.published_at)

    def test_active_edit_page_only_shows_save_changes_button(self):
        self.listing.status = Listing.Status.ACTIVE
        self.listing.published_at = timezone.now()
        self.listing.save(update_fields=["status", "published_at"])
        self.client.force_login(self.user)

        response = self.client.get(self.url())

        self.assertContains(response, "保存修改")
        self.assertNotContains(response, 'value="save_draft"')
        self.assertNotContains(response, 'value="publish"')

    def test_active_listing_save_changes_keeps_status_and_published_at(self):
        published_at = timezone.now() - timezone.timedelta(days=1)
        self.listing.status = Listing.Status.ACTIVE
        self.listing.published_at = published_at
        self.listing.save(update_fields=["status", "published_at"])
        self.client.force_login(self.user)

        response = self.client.post(
            self.url(),
            self.valid_post_data(
                intent="save_changes",
                owner=str(self.other_user.pk),
                status=Listing.Status.DRAFT,
                published_at="1999-01-01T00:00:00Z",
            ),
        )

        self.assertRedirects(response, self.url())
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "更新后的旧椅子")
        self.assertEqual(self.listing.owner, self.user)
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)
        self.assertEqual(self.listing.published_at, published_at)

    def test_active_listing_rejects_publish_intent(self):
        published_at = timezone.now()
        self.listing.status = Listing.Status.ACTIVE
        self.listing.published_at = published_at
        self.listing.save(update_fields=["status", "published_at"])
        self.client.force_login(self.user)

        response = self.client.post(self.url(), self.valid_post_data(intent="publish"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "无效的提交操作")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)
        self.assertEqual(self.listing.published_at, published_at)

    def test_inactive_category_submission_is_rejected_on_edit(self):
        inactive_category = Category.objects.create(name="停用家具", is_active=False)
        self.client.force_login(self.user)

        response = self.client.post(
            self.url(),
            self.valid_post_data(category=str(inactive_category.pk)),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "选择一个有效的选项")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.category, self.category)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ListingDeleteViewTest(TestCase):
    """商品删除视图测试。"""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="seller6",
            email="seller6@example.com",
            password="StrongPass123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other6",
            email="other6@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="运动用品")
        self.listing = Listing.objects.create(
            owner=self.user,
            category=self.category,
            title="篮球",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.DRAFT,
            price=Decimal("50.00"),
            condition=Listing.Condition.GOOD,
            description="九成新。",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
        )

    def url(self, listing=None):
        listing = listing or self.listing
        return reverse("catalog:listing_delete", kwargs={"pk": listing.pk})

    def test_guest_is_redirected_to_login_with_next(self):
        response = self.client.get(self.url())

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.url()}")

    def test_get_renders_confirmation_and_does_not_delete(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/listing_confirm_delete.html")
        self.assertContains(response, "确认删除商品")
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())

    def test_non_owner_get_returns_403(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 403)

    def test_non_owner_post_returns_403_and_does_not_delete(self):
        self.client.force_login(self.other_user)

        response = self.client.post(self.url())

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Listing.objects.filter(pk=self.listing.pk).exists())

    def test_post_deletes_own_draft_listing_and_images(self):
        image = ListingImage.objects.create(
            listing=self.listing,
            image=create_test_image("delete-me.png"),
            sort_order=0,
        )
        image_name = image.image.name
        self.client.force_login(self.user)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url())

        self.assertRedirects(response, reverse("users:profile"))
        self.assertFalse(Listing.objects.filter(pk=self.listing.pk).exists())
        self.assertFalse(ListingImage.objects.filter(pk=image.pk).exists())
        self.assertFalse(image.image.storage.exists(image_name))

    def test_post_deletes_own_active_listing(self):
        self.listing.status = Listing.Status.ACTIVE
        self.listing.published_at = timezone.now()
        self.listing.save(update_fields=["status", "published_at"])
        self.client.force_login(self.user)

        response = self.client.post(self.url())

        self.assertRedirects(response, reverse("users:profile"))
        self.assertFalse(Listing.objects.filter(pk=self.listing.pk).exists())


class OwnerListingGroupsSelectorTest(TestCase):
    """“我的商品”分组 selector 测试。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="grpseller",
            email="grouped@example.com",
            password="StrongPass123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="grpother",
            email="grouped_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="电子产品")

    def make_listing(self, *, owner, status, title):
        return Listing.objects.create(
            owner=owner,
            category=self.category,
            title=title,
            item_type=Listing.ItemType.PHYSICAL,
            status=status,
            price=Decimal("10.00"),
            condition=Listing.Condition.GOOD,
            description="测试商品",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
        )

    def test_groups_returned_in_fixed_lifecycle_order(self):
        groups = get_owner_listing_groups(self.user)

        self.assertEqual(
            [group["status"] for group in groups],
            [
                Listing.Status.DRAFT,
                Listing.Status.ACTIVE,
                Listing.Status.RESERVED,
                Listing.Status.SOLD,
                Listing.Status.WITHDRAWN,
            ],
        )

    def test_empty_groups_are_still_present_with_zero_count(self):
        groups = get_owner_listing_groups(self.user)

        for group in groups:
            self.assertEqual(group["count"], 0)
            self.assertEqual(list(group["listings"]), [])
            self.assertTrue(group["empty_text"])
            self.assertTrue(group["title"])

    def test_listings_are_split_into_their_status_buckets(self):
        draft = self.make_listing(owner=self.user, status=Listing.Status.DRAFT, title="草稿一号")
        active = self.make_listing(owner=self.user, status=Listing.Status.ACTIVE, title="在售一号")
        reserved = self.make_listing(
            owner=self.user, status=Listing.Status.RESERVED, title="占用一号"
        )
        sold = self.make_listing(owner=self.user, status=Listing.Status.SOLD, title="已售一号")
        withdrawn = self.make_listing(
            owner=self.user, status=Listing.Status.WITHDRAWN, title="下架一号"
        )

        groups = {group["status"]: group for group in get_owner_listing_groups(self.user)}

        self.assertEqual(list(groups[Listing.Status.DRAFT]["listings"]), [draft])
        self.assertEqual(list(groups[Listing.Status.ACTIVE]["listings"]), [active])
        self.assertEqual(list(groups[Listing.Status.RESERVED]["listings"]), [reserved])
        self.assertEqual(list(groups[Listing.Status.SOLD]["listings"]), [sold])
        self.assertEqual(list(groups[Listing.Status.WITHDRAWN]["listings"]), [withdrawn])

    def test_only_current_user_listings_are_returned(self):
        own = self.make_listing(owner=self.user, status=Listing.Status.ACTIVE, title="自己")
        self.make_listing(owner=self.other_user, status=Listing.Status.ACTIVE, title="他人")

        groups = {group["status"]: group for group in get_owner_listing_groups(self.user)}

        self.assertEqual(list(groups[Listing.Status.ACTIVE]["listings"]), [own])

    def test_listings_inside_group_are_sorted_by_updated_at_desc(self):
        first = self.make_listing(
            owner=self.user, status=Listing.Status.ACTIVE, title="先发布"
        )
        second = self.make_listing(
            owner=self.user, status=Listing.Status.ACTIVE, title="后发布"
        )
        Listing.objects.filter(pk=second.pk).update(
            updated_at=timezone.now() + timezone.timedelta(seconds=1)
        )

        groups = {group["status"]: group for group in get_owner_listing_groups(self.user)}

        active_listings = list(groups[Listing.Status.ACTIVE]["listings"])
        self.assertEqual(active_listings[0].pk, second.pk)
        self.assertEqual(active_listings[1].pk, first.pk)


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

        listings = list(get_publish_listing_queryset())

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

        listings = list(get_publish_listing_queryset())

        self.assertEqual(listings, [active])

    def test_queryset_uses_stable_published_at_and_id_desc_order(self):
        published_at = timezone.now() - timezone.timedelta(days=1)
        older = self.make_listing(
            title="较早商品",
            published_at=published_at - timezone.timedelta(hours=1),
        )
        first_same_time = self.make_listing(title="同时间一号", published_at=published_at)
        second_same_time = self.make_listing(title="同时间二号", published_at=published_at)

        listings = list(get_publish_listing_queryset())

        self.assertEqual(listings, [second_same_time, first_same_time, older])

    def test_keyword_matches_title_or_description(self):
        match_title = self.make_listing(title="蓝牙耳机", description="无关描述")
        match_desc = self.make_listing(title="无关标题", description="蓝牙音箱描述")
        no_match = self.make_listing(title="无关标题", description="无关描述")

        results = list(get_publish_listing_queryset({"q": "蓝牙"}))

        self.assertIn(match_title, results)
        self.assertIn(match_desc, results)
        self.assertNotIn(no_match, results)

    def test_category_filter(self):
        other_category = Category.objects.create(name="另一分类")
        target = self.make_listing(title="目标分类商品", category=self.category)
        other = self.make_listing(title="其他分类商品", category=other_category)

        results = list(get_publish_listing_queryset({"category": self.category}))

        self.assertIn(target, results)
        self.assertNotIn(other, results)

    def test_item_type_filter(self):
        physical = self.make_listing(title="实体", item_type=Listing.ItemType.PHYSICAL)
        virtual = self.make_listing(title="虚拟", item_type=Listing.ItemType.VIRTUAL)

        results = list(get_publish_listing_queryset({"item_type": "virtual"}))

        self.assertNotIn(physical, results)
        self.assertIn(virtual, results)

    def test_price_range_filter(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        mid = self.make_listing(title="中等", price=Decimal("50.00"))
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))

        results = list(
            get_publish_listing_queryset({"min_price": Decimal("20"), "max_price": Decimal("100")})
        )

        self.assertNotIn(cheap, results)
        self.assertIn(mid, results)
        self.assertNotIn(expensive, results)

    def test_sort_price_asc(self):
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))

        results = list(get_publish_listing_queryset({"sort": "price_asc"}))

        self.assertEqual(results, [cheap, expensive])

    def test_sort_price_desc(self):
        cheap = self.make_listing(title="便宜", price=Decimal("10.00"))
        expensive = self.make_listing(title="贵", price=Decimal("200.00"))

        results = list(get_publish_listing_queryset({"sort": "price_desc"}))

        self.assertEqual(results, [expensive, cheap])

    def test_sort_oldest(self):
        older = self.make_listing(
            title="旧", published_at=timezone.now() - timezone.timedelta(days=2)
        )
        newer = self.make_listing(
            title="新", published_at=timezone.now() - timezone.timedelta(days=1)
        )

        results = list(get_publish_listing_queryset({"sort": "oldest"}))

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

        results = list(get_publish_listing_queryset({"sort": "invalid_sort"}))

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
            get_publish_listing_queryset({
                "q": "蓝牙",
                "item_type": "physical",
                "min_price": Decimal("10"),
                "max_price": Decimal("100"),
            })
        )

        self.assertEqual(results, [target])


class ListingFilterFormTest(TestCase):
    """筛选表单校验测试。"""

    def setUp(self):
        self.category = Category.objects.create(name="有效分类")
        self.inactive_category = Category.objects.create(name="停用分类", is_active=False)

    def test_valid_empty_form(self):
        form = ListingFilterForm(data={})
        self.assertTrue(form.is_valid())

    def test_valid_full_form(self):
        form = ListingFilterForm(data={
            "q": "蓝牙",
            "category": self.category.pk,
            "item_type": "physical",
            "min_price": "10",
            "max_price": "200",
            "sort": "price_asc",
        })
        self.assertTrue(form.is_valid())

    def test_q_strips_whitespace(self):
        form = ListingFilterForm(data={"q": "  蓝牙耳机  "})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["q"], "蓝牙耳机")

    def test_q_exceeds_max_length(self):
        form = ListingFilterForm(data={"q": "x" * 101})
        self.assertFalse(form.is_valid())
        self.assertIn("q", form.errors)

    def test_inactive_category_rejected(self):
        form = ListingFilterForm(data={"category": self.inactive_category.pk})
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_nonexistent_category_rejected(self):
        form = ListingFilterForm(data={"category": "99999"})
        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_invalid_item_type_rejected(self):
        form = ListingFilterForm(data={"item_type": "hacked"})
        self.assertFalse(form.is_valid())
        self.assertIn("item_type", form.errors)

    def test_negative_min_price_rejected(self):
        form = ListingFilterForm(data={"min_price": "-5"})
        self.assertFalse(form.is_valid())
        self.assertIn("min_price", form.errors)

    def test_non_numeric_price_rejected(self):
        form = ListingFilterForm(data={"min_price": "abc"})
        self.assertFalse(form.is_valid())
        self.assertIn("min_price", form.errors)

    def test_min_price_greater_than_max_price_error(self):
        form = ListingFilterForm(data={"min_price": "100", "max_price": "10"})
        self.assertFalse(form.is_valid())
        self.assertIn("最高价格不得低于最低价格", form.non_field_errors())

    def test_unknown_sort_rejected(self):
        form = ListingFilterForm(data={"sort": "hacked_field"})
        self.assertFalse(form.is_valid())
        self.assertIn("sort", form.errors)

    def test_defaults_when_fields_empty(self):
        form = ListingFilterForm(data={})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["min_price"], 0)
        self.assertEqual(form.cleaned_data["max_price"], 99999999)
        self.assertEqual(form.cleaned_data["page"], 1)


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


class MyListingListViewTest(TestCase):
    """“我的商品”分组面板视图测试。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pnseller",
            email="panel@example.com",
            password="StrongPass123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="pnother",
            email="panel_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="收藏品")
        self.url = reverse("catalog:my_listing_list")

    def make_listing(self, *, owner, status, title):
        return Listing.objects.create(
            owner=owner,
            category=self.category,
            title=title,
            item_type=Listing.ItemType.PHYSICAL,
            status=status,
            price=Decimal("88.00"),
            condition=Listing.Condition.GOOD,
            description="九成新",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
        )

    def test_guest_is_redirected_to_login_with_next(self):
        response = self.client.get(self.url)

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.url}")

    def test_authenticated_user_sees_all_five_group_titles_even_when_empty(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/my_listing_list.html")
        for title in ["草稿", "在售", "交易占用", "已售出", "已下架"]:
            self.assertContains(response, title)

    def test_page_only_shows_current_user_listings(self):
        own = self.make_listing(
            owner=self.user, status=Listing.Status.ACTIVE, title="自己的相机"
        )
        self.make_listing(
            owner=self.other_user, status=Listing.Status.ACTIVE, title="他人的相机"
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, own.title)
        self.assertNotContains(response, "他人的相机")

    def test_active_listing_renders_withdraw_action_form(self):
        listing = self.make_listing(
            owner=self.user, status=Listing.Status.ACTIVE, title="可下架"
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        status_url = reverse(
            "catalog:listing_status_update", kwargs={"pk": listing.pk}
        )
        self.assertContains(response, f'action="{status_url}"')
        self.assertContains(response, f'value="{ACTION_WITHDRAW}"')

    def test_withdrawn_listing_renders_restore_action_form(self):
        self.make_listing(
            owner=self.user, status=Listing.Status.WITHDRAWN, title="可重新上架"
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, f'value="{ACTION_RESTORE_ACTIVE}"')
        self.assertContains(response, "重新上架")

    def test_reserved_and_sold_render_readonly_explanation_only(self):
        self.make_listing(
            owner=self.user, status=Listing.Status.RESERVED, title="占用商品"
        )
        self.make_listing(
            owner=self.user, status=Listing.Status.SOLD, title="已售商品"
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertContains(response, "交易占用由订单流程控制")
        self.assertContains(response, "已售出商品不可重新上架")


class PublicListingListViewTest(TestCase):
    """公开商品列表视图测试。"""

    def setUp(self):
        self.seller = get_user_model().objects.create_user(
            username="pubview",
            email="public_view@example.com",
            password="StrongPass123",
        )
        self.other_seller = get_user_model().objects.create_user(
            username="pubother",
            email="public_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="公开数码")
        self.inactive_category = Category.objects.create(name="停用数码", is_active=False)
        self.url = reverse("catalog:listing_list")

        self.seller.profile.nickname = "公开卖家"
        self.seller.profile.bio = "只展示公开简介"
        self.seller.profile.save(update_fields=["nickname", "bio", "updated_at"])

    def make_listing(self, **overrides):
        data = {
            "owner": self.seller,
            "category": self.category,
            "title": "公开相机",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("188.00"),
            "condition": Listing.Condition.GOOD,
            "description": "公开列表测试商品",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.datetime(
                2026, 5, 1, 10, 30, tzinfo=timezone.get_current_timezone()
            ),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def test_guest_can_visit_public_listing_page_without_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "catalog/listing_list.html")
        self.assertEqual(response.context["querystring_without_page"], "")

    def test_page_renders_public_listing_fields_and_placeholder(self):
        listing = self.make_listing(title="公开无图相机")

        response = self.client.get(self.url)

        self.assertContains(response, listing.title)
        self.assertContains(response, "¥188.00")
        self.assertContains(response, "公开数码")
        self.assertContains(response, "实体商品")
        self.assertContains(response, "2026-05-01 10:30")
        self.assertContains(response, "公开卖家")
        self.assertContains(response, "只展示公开简介")
        self.assertContains(response, "暂无图片")

    def test_page_excludes_non_public_statuses_and_inactive_category(self):
        visible = self.make_listing(title="可浏览商品")
        hidden_cases = [
            ("草稿商品", Listing.Status.DRAFT, self.category),
            ("下架商品", Listing.Status.WITHDRAWN, self.category),
            ("占用商品", Listing.Status.RESERVED, self.category),
            ("已售商品", Listing.Status.SOLD, self.category),
            ("停用分类在售商品", Listing.Status.ACTIVE, self.inactive_category),
        ]
        for title, status, category in hidden_cases:
            self.make_listing(title=title, status=status, category=category)

        response = self.client.get(self.url)

        self.assertContains(response, visible.title)
        for title, _status, _category in hidden_cases:
            self.assertNotContains(response, title)

    def test_page_shows_other_seller_active_listing_without_private_fields(self):
        other_listing = self.make_listing(
            owner=self.other_seller,
            title="其他卖家的公开商品",
        )
        self.other_seller.profile.nickname = "其他公开卖家"
        self.other_seller.profile.save(update_fields=["nickname", "updated_at"])

        response = self.client.get(self.url)

        self.assertContains(response, other_listing.title)
        self.assertContains(response, "其他公开卖家")
        self.assertNotContains(response, self.other_seller.email)
        self.assertNotContains(response, f"用户 ID")

    def test_page_does_not_render_seller_management_actions(self):
        self.make_listing(title="只读公开商品")

        response = self.client.get(self.url)

        for text in ["继续编辑/发布", "删除草稿", "编辑", "删除", "下架", "重新上架"]:
            self.assertNotContains(response, text)
        self.assertNotContains(response, 'name="action"')

    def test_empty_page_has_stable_empty_state(self):
        response = self.client.get(self.url)

        self.assertContains(response, "暂时没有可浏览的在售商品。")

    def test_invalid_page_parameter_returns_first_page(self):
        first = self.make_listing(title="第一页商品")
        self.make_listing(title="第二页商品", published_at=timezone.now() - timezone.timedelta(days=2))

        response = self.client.get(self.url, {"page": "abc"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertIn(first, list(response.context["listings"]))

    def test_out_of_range_page_parameter_returns_last_page(self):
        for index in range(13):
            self.make_listing(
                title=f"分页商品{index:02d}",
                published_at=timezone.now() - timezone.timedelta(minutes=index),
            )

        response = self.client.get(self.url, {"page": "999"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["paginator"].num_pages, 2)

    def test_pagination_links_preserve_existing_query_params_without_page(self):
        for index in range(13):
            self.make_listing(
                title=f"保留参数商品{index:02d}",
                published_at=timezone.now() - timezone.timedelta(minutes=index),
            )

        response = self.client.get(self.url, {"q": "保留参数", "sort": "newest", "page": "1"})

        self.assertIn("q=", response.context["querystring_without_page"])
        self.assertNotIn("page=", response.context["querystring_without_page"])
        self.assertContains(response, "page=2")
        self.assertNotContains(response, "page=1&amp;page=2")
        self.assertContains(response, "下一页")
        self.assertContains(response, "末页")

    def test_second_page_renders_previous_and_first_page_links(self):
        for index in range(13):
            self.make_listing(
                title=f"反向分页商品{index:02d}",
                published_at=timezone.now() - timezone.timedelta(minutes=index),
            )

        response = self.client.get(self.url, {"q": "反向分页", "page": "2"})

        self.assertContains(response, "page=1")
        self.assertContains(response, "首页")
        self.assertContains(response, "上一页")

    def test_keyword_search_filters_by_title(self):
        match = self.make_listing(title="蓝牙耳机公开")
        no_match = self.make_listing(title="无关商品公开")

        response = self.client.get(self.url, {"q": "蓝牙"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, match.title)
        self.assertNotContains(response, no_match.title)

    def test_keyword_search_filters_by_description(self):
        match = self.make_listing(title="普通标题A", description="包含蓝牙功能的描述")
        no_match = self.make_listing(title="普通标题B", description="完全无关的描述")

        response = self.client.get(self.url, {"q": "蓝牙"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, match.title)
        self.assertNotContains(response, no_match.title)

    def test_category_filter_returns_only_target_category(self):
        other_category = Category.objects.create(name="其他分类")
        target = self.make_listing(title="目标分类商品", category=self.category)
        other = self.make_listing(title="其他分类商品", category=other_category)

        response = self.client.get(self.url, {"category": self.category.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, target.title)
        self.assertNotContains(response, other.title)

    def test_disabled_category_not_in_filter_options(self):
        self.make_listing(title="任意商品")

        response = self.client.get(self.url)

        self.assertContains(response, "公开数码")
        self.assertNotContains(response, "停用数码")

    def test_submitting_disabled_category_does_not_500(self):
        response = self.client.get(self.url, {"category": self.inactive_category.pk})

        self.assertEqual(response.status_code, 200)

    def test_item_type_filter_physical(self):
        physical = self.make_listing(title="实体公开", item_type=Listing.ItemType.PHYSICAL)
        virtual = self.make_listing(title="虚拟公开", item_type=Listing.ItemType.VIRTUAL)

        response = self.client.get(self.url, {"item_type": "physical"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, physical.title)
        self.assertNotContains(response, virtual.title)

    def test_price_range_filter(self):
        cheap = self.make_listing(title="便宜公开", price=Decimal("10.00"))
        mid = self.make_listing(title="中等公开", price=Decimal("50.00"))
        expensive = self.make_listing(title="贵公开", price=Decimal("200.00"))

        response = self.client.get(self.url, {"min_price": "20", "max_price": "100"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, cheap.title)
        self.assertContains(response, mid.title)
        self.assertNotContains(response, expensive.title)

    def test_min_price_greater_than_max_price_shows_chinese_error(self):
        self.make_listing(title="任意商品")

        response = self.client.get(self.url, {"min_price": "100", "max_price": "10"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "最高价格不得低于最低价格")

    def test_sort_price_asc(self):
        expensive = self.make_listing(title="贵排序", price=Decimal("200.00"))
        cheap = self.make_listing(title="便宜排序", price=Decimal("10.00"))

        response = self.client.get(self.url, {"sort": "price_asc"})

        listings = list(response.context["listings"])
        self.assertEqual(listings, [cheap, expensive])

    def test_sort_price_desc(self):
        cheap = self.make_listing(title="便宜排序", price=Decimal("10.00"))
        expensive = self.make_listing(title="贵排序", price=Decimal("200.00"))

        response = self.client.get(self.url, {"sort": "price_desc"})

        listings = list(response.context["listings"])
        self.assertEqual(listings, [expensive, cheap])

    def test_default_sort_is_newest_first(self):
        older = self.make_listing(
            title="旧商品",
            published_at=timezone.now() - timezone.timedelta(days=2),
        )
        newer = self.make_listing(
            title="新商品",
            published_at=timezone.now() - timezone.timedelta(days=1),
        )

        response = self.client.get(self.url)

        listings = list(response.context["listings"])
        self.assertEqual(listings, [newer, older])

    def test_unknown_sort_value_does_not_500(self):
        self.make_listing(title="任意商品")

        response = self.client.get(self.url, {"sort": "hacked_field"})

        self.assertEqual(response.status_code, 200)

    def test_filter_results_exclude_non_purchasable_statuses(self):
        active = self.make_listing(title="搜索目标在售", description="可搜索描述")
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.WITHDRAWN,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
        ]:
            self.make_listing(title="搜索目标非售", description="可搜索描述", status=status)

        response = self.client.get(self.url, {"q": "搜索目标"})

        listings = list(response.context["listings"])
        self.assertEqual(listings, [active])

    def test_filter_form_preserves_current_values(self):
        self.make_listing(title="蓝牙耳机")

        response = self.client.get(self.url, {"q": "蓝牙", "sort": "price_asc"})

        form = response.context["filter_form"]
        self.assertEqual(form.data.get("q"), "蓝牙")
        self.assertEqual(form.data.get("sort"), "price_asc")

    def test_active_filters_summary_displayed(self):
        self.make_listing(title="蓝牙耳机")

        response = self.client.get(self.url, {"q": "蓝牙"})

        self.assertContains(response, "当前筛选")
        self.assertContains(response, "蓝牙")

    def test_clear_filters_link_present(self):
        self.make_listing(title="蓝牙耳机")

        response = self.client.get(self.url, {"q": "蓝牙"})

        self.assertContains(response, "清除筛选")
        self.assertContains(response, "清除全部")


class ListingStatusUpdateViewTest(TestCase):
    """商品状态变更视图测试。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="updseller",
            email="updater@example.com",
            password="StrongPass123",
        )
        self.other_user = get_user_model().objects.create_user(
            username="updother",
            email="updater_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="家电")
        self.listing = Listing.objects.create(
            owner=self.user,
            category=self.category,
            title="二手吹风机",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("60.00"),
            condition=Listing.Condition.GOOD,
            description="九成新",
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
            published_at=timezone.now() - timezone.timedelta(days=1),
        )

    def url(self, listing=None):
        listing = listing or self.listing
        return reverse("catalog:listing_status_update", kwargs={"pk": listing.pk})

    def test_guest_post_is_redirected_to_login_with_next(self):
        response = self.client.post(self.url(), {"action": ACTION_WITHDRAW})

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.url()}")
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)

    def test_get_does_not_change_status(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 405)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)

    def test_post_withdraw_succeeds_and_redirects_with_message(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url(), {"action": ACTION_WITHDRAW})

        self.assertRedirects(response, reverse("catalog:my_listing_list"))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.WITHDRAWN)
        flash = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("商品已下架", flash)

    def test_post_restore_active_succeeds_and_redirects_with_message(self):
        self.listing.status = Listing.Status.WITHDRAWN
        self.listing.save(update_fields=["status"])
        self.client.force_login(self.user)

        response = self.client.post(self.url(), {"action": ACTION_RESTORE_ACTIVE})

        self.assertRedirects(response, reverse("catalog:my_listing_list"))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)
        flash = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("商品已重新上架", flash)

    def test_post_invalid_action_keeps_status_and_shows_chinese_error(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url(), {"action": "mark_sold"})

        self.assertRedirects(response, reverse("catalog:my_listing_list"))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)
        flash = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("无效的状态动作", flash)

    def test_post_withdraw_on_draft_keeps_status_and_shows_error(self):
        self.listing.status = Listing.Status.DRAFT
        self.listing.published_at = None
        self.listing.save(update_fields=["status", "published_at"])
        self.client.force_login(self.user)

        response = self.client.post(self.url(), {"action": ACTION_WITHDRAW})

        self.assertRedirects(response, reverse("catalog:my_listing_list"))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.DRAFT)

    def test_post_seller_cannot_inject_status_owner_or_published_at(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.url(),
            {
                "action": ACTION_WITHDRAW,
                "status": Listing.Status.SOLD,
                "owner": str(self.other_user.pk),
                "published_at": "1999-01-01T00:00:00Z",
            },
        )

        self.assertRedirects(response, reverse("catalog:my_listing_list"))
        self.listing.refresh_from_db()
        # 即使 POST 带上伪造字段，也只走白名单动作 withdraw -> withdrawn。
        self.assertEqual(self.listing.status, Listing.Status.WITHDRAWN)
        self.assertEqual(self.listing.owner_id, self.user.id)
        self.assertNotEqual(self.listing.published_at.year, 1999)

    def test_non_owner_post_returns_403_and_does_not_change_status(self):
        self.client.force_login(self.other_user)

        response = self.client.post(self.url(), {"action": ACTION_WITHDRAW})

        self.assertEqual(response.status_code, 403)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)

    def test_unknown_listing_returns_404(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("catalog:listing_status_update", kwargs={"pk": 99999}),
            {"action": ACTION_WITHDRAW},
        )

        self.assertEqual(response.status_code, 404)

    def test_restore_active_with_disabled_category_keeps_withdrawn(self):
        self.listing.status = Listing.Status.WITHDRAWN
        self.listing.save(update_fields=["status"])
        self.category.is_active = False
        self.category.save(update_fields=["is_active", "updated_at"])
        self.client.force_login(self.user)

        response = self.client.post(self.url(), {"action": ACTION_RESTORE_ACTIVE})

        self.assertRedirects(response, reverse("catalog:my_listing_list"))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.WITHDRAWN)
        flash = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("分类" in message for message in flash))

from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import Category, Listing, ListingImage
from users.models import User


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

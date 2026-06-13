from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from PIL import Image

from catalog.models import Category, Listing
from users.models import User


class UsersApiTests(APITestCase):
    """P2 用户与认证 API 测试。"""

    def setUp(self):
        self.client = APIClient()
        Group.objects.create(name="普通用户组")

    def _auth_headers(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _build_png_image(self, name="avatar.png"):
        buffer = BytesIO()
        image = Image.new("RGB", (1, 1), color="white")
        image.save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_register_creates_user_profile_and_default_group(self):
        response = self.client.post(
            reverse("api:auth_register"),
            data={
                "username": "buyer",
                "email": "Buyer@Example.com",
                "password": "StrongPass123",
                "password_confirm": "StrongPass123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["username"], "buyer")
        user = User.objects.get(username="buyer")
        self.assertEqual(user.email, "buyer@example.com")
        self.assertTrue(user.profile)
        self.assertTrue(user.groups.filter(name="普通用户组").exists())

    def test_register_rejects_duplicate_email_and_password_mismatch(self):
        User.objects.create_user(
            username="taken",
            email="taken@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("api:auth_register"),
            data={
                "username": "fresh",
                "email": "taken@example.com",
                "password": "StrongPass123",
                "password_confirm": "Mismatch123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("message", body)
        self.assertIn("errors", body)

    def test_token_uses_identifier_for_username_login(self):
        user = User.objects.create_user(
            username="loginu",
            email="loginu@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("api:auth_token"),
            data={"identifier": user.username, "password": "StrongPass123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())

    def test_token_uses_identifier_for_email_login(self):
        User.objects.create_user(
            username="emaillogin",
            email="email-login@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("api:auth_token"),
            data={"identifier": "EMAIL-LOGIN@example.com", "password": "StrongPass123"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_token_rejects_invalid_credentials_with_json_error(self):
        response = self.client.post(
            reverse("api:auth_token"),
            data={"identifier": "missing", "password": "wrong"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.json())
        self.assertIn("errors", response.json())

    def test_refresh_token_returns_new_access_token(self):
        user = User.objects.create_user(
            username="refreshu",
            email="refreshu@example.com",
            password="StrongPass123",
        )
        refresh = RefreshToken.for_user(user)

        response = self.client.post(
            reverse("api:auth_token_refresh"),
            data={"refresh": str(refresh)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_me_get_returns_current_user_profile(self):
        user = User.objects.create_user(
            username="profileu",
            email="profileu@example.com",
            password="StrongPass123",
        )
        user.profile.nickname = "我的昵称"
        user.profile.bio = "公开简介"
        user.profile.save()

        response = self.client.get(
            reverse("api:users_me"),
            **self._auth_headers(user),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["username"], "profileu")
        self.assertEqual(body["profile"]["nickname"], "我的昵称")
        self.assertEqual(body["profile"]["bio"], "公开简介")

    def test_me_patch_updates_profile_and_avatar(self):
        user = User.objects.create_user(
            username="updateu",
            email="updateu@example.com",
            password="StrongPass123",
        )
        avatar = self._build_png_image()

        with self.settings(
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.InMemoryStorage",
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            }
        ):
            response = self.client.patch(
                reverse("api:users_me"),
                data={"nickname": "新昵称", "bio": "新简介", "avatar": avatar},
                format="multipart",
                **self._auth_headers(user),
            )

        self.assertEqual(response.status_code, 200)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.nickname, "新昵称")
        self.assertEqual(user.profile.bio, "新简介")

    def test_public_user_profile_includes_active_listings(self):
        seller = User.objects.create_user(
            username="seller",
            email="seller@example.com",
            password="StrongPass123",
        )
        category = Category.objects.create(name="公开分类")
        Listing.objects.create(
            owner=seller,
            category=category,
            title="公开商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="商品描述",
            condition=Listing.Condition.GOOD,
            delivery_notes="面交",
            physical_delivery_method=Listing.PhysicalDeliveryMethod.MEETUP,
            published_at=timezone.now(),
        )

        response = self.client.get(reverse("api:users_public", kwargs={"user_id": seller.id}))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["username"], "seller")
        self.assertEqual(body["listings"][0]["title"], "公开商品")
        self.assertEqual(body["listings"][0]["category_name"], "公开分类")

    def test_public_user_profile_returns_404_for_missing_user(self):
        response = self.client.get(reverse("api:users_public", kwargs={"user_id": 99999}))

        self.assertEqual(response.status_code, 404)

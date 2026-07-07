from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.test import RequestFactory, TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import Category, Listing
from users.admin import MyUserAdmin, ProfileInline
from users.models import Profile, User, avatar_upload_to
from users.signals import create_user_profile


class UserModelTest(TestCase):
    """用户模型基础行为测试。

    覆盖用户模型配置、密码哈希、展示文本、用户名长度校验和邮箱唯一约束。
    """

    def test_auth_user_model_points_to_custom_user_model(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "users.User")

    def test_get_user_model_returns_custom_user_model(self):
        self.assertIs(get_user_model(), User)

    def test_create_user_hashes_password(self):
        user = User.objects.create_user(
            username="hash",
            email="hash@example.com",
            password="plain-password",
        )

        self.assertNotEqual(user.password, "plain-password")
        self.assertTrue(user.check_password("plain-password"))

    def test_create_superuser_keeps_admin_permissions_and_password_hash(self):
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin-password",
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("admin-password"))
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_user_str_returns_username_label(self):
        user = User(username="张三", email="zhangsan@example.com")

        self.assertEqual(str(user), "张三的账号")

    def test_username_must_not_be_shorter_than_two_chars(self):
        user = User(username="a", email="short@example.com", password="test-pass")

        with self.assertRaises(ValidationError) as context:
            user.full_clean()

        self.assertIn("username", context.exception.message_dict)

    def test_email_must_be_unique(self):
        User.objects.create_user(username="user1", email="same@example.com", password="test-pass")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="user2",
                    email="same@example.com",
                    password="test-pass",
                )


class ProfileModelTest(TestCase):
    """用户资料模型和头像路径测试。

    覆盖资料展示文本、头像路径目录、扩展名标准化和默认扩展名。
    """

    def test_profile_str_returns_owner_username_label(self):
        user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="test-pass",
        )

        self.assertEqual(str(user.profile), "owner的用户资料")

    def test_created_profile_uses_default_nickname(self):
        user = User.objects.create_user(
            username="nick",
            email="nick@example.com",
            password="test-pass",
        )

        self.assertEqual(user.profile.nickname, "初始昵称")

    def test_avatar_upload_to_uses_user_id_uuid_and_lowercase_extension(self):
        user = User.objects.create_user(
            username="avatar",
            email="avatar@example.com",
            password="test-pass",
        )

        upload_path = avatar_upload_to(user.profile, "MyAvatar.PNG")

        self.assertTrue(upload_path.startswith(f"avatars/users/{user.id}/"))
        self.assertEqual(Path(upload_path).suffix, ".png")

    def test_avatar_upload_to_defaults_to_jpg_when_filename_has_no_extension(self):
        user = User.objects.create_user(
            username="noext",
            email="noext@example.com",
            password="test-pass",
        )

        upload_path = avatar_upload_to(user.profile, "avatar")

        self.assertTrue(upload_path.endswith(".jpg"))


class UserProfileSignalTest(TestCase):
    """用户创建信号的资料自动创建测试。

    覆盖普通用户创建、fixture/raw 保存跳过，以及重复触发时的幂等行为。
    """

    def test_profile_is_created_when_user_is_created(self):
        user = User.objects.create_user(
            username="signal",
            email="signal@example.com",
            password="test-pass",
        )

        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_raw_user_save_does_not_create_profile(self):
        user = User.objects.create_user(
            username="raw",
            email="raw@example.com",
            password="test-pass",
        )
        user.profile.delete()

        create_user_profile(sender=User, instance=user, created=True, raw=True)

        self.assertFalse(Profile.objects.filter(user=user).exists())

    def test_existing_profile_does_not_break_created_signal(self):
        user = User.objects.create_user(
            username="exists",
            email="exists@example.com",
            password="test-pass",
        )

        create_user_profile(sender=User, instance=user, created=True, raw=False)

        self.assertEqual(Profile.objects.filter(user=user).count(), 1)


class UserAdminTest(TestCase):
    """用户后台注册、治理字段和访问烟雾测试。"""

    def test_user_admin_is_registered_with_profile_inline(self):
        user_admin = admin.site._registry[User]

        self.assertIsInstance(user_admin, MyUserAdmin)
        self.assertIn(ProfileInline, user_admin.inlines)

    def test_user_admin_exposes_required_columns_filters_search_and_readonly_fields(self):
        user_admin = admin.site._registry[User]

        for field in [
            "id",
            "username",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "created_at",
            "updated_at",
        ]:
            self.assertIn(field, user_admin.list_display)

        for field in ["is_active", "is_staff", "is_superuser", "groups", "created_at"]:
            self.assertIn(field, user_admin.list_filter)

        for field in ["id", "username", "email"]:
            self.assertIn(field, user_admin.search_fields)

        for field in ["created_at", "updated_at", "last_login"]:
            self.assertIn(field, user_admin.readonly_fields)

        permission_fields = user_admin.fieldsets[2][1]["fields"]
        self.assertIn("is_active", permission_fields)

    def test_superuser_can_open_user_admin_changelist(self):
        superuser = User.objects.create_superuser(
            username="useradmin",
            email="useradmin@example.com",
            password="StrongPass123",
        )
        self.client.force_login(superuser)

        response = self.client.get(reverse("admin:users_user_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_open_user_admin_changelist(self):
        user = User.objects.create_user(
            username="normadm",
            email="normaladmin@example.com",
            password="StrongPass123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:users_user_changelist"))

        self.assertIn(response.status_code, [302, 403])


class ProfileInlineAdminTest(TestCase):
    """后台用户资料内联表单的边界行为测试。

    覆盖用户新增页、已有资料用户、缺少资料用户三个后台展示路径。
    """

    def setUp(self):
        """构造后台 inline 实例和请求对象。

        Returns:
            None: 该方法只为测试用例准备共享状态。
        """

        self.inline = ProfileInline(User, AdminSite())
        self.request = RequestFactory().get("/admin/users/user/1/change/")

    def test_profile_inline_does_not_render_extra_form_on_user_create_page(self):
        self.assertEqual(self.inline.get_extra(self.request, obj=None), 0)

    def test_profile_inline_does_not_allow_second_profile_when_profile_exists(self):
        user = User.objects.create_user(
            username="filled",
            email="filled@example.com",
            password="test-pass",
        )

        self.assertFalse(self.inline.has_add_permission(self.request, obj=user))
        self.assertEqual(self.inline.get_extra(self.request, obj=user), 0)

    def test_profile_inline_allows_one_profile_when_profile_is_missing(self):
        user = User.objects.create_user(
            username="miss",
            email="missing@example.com",
            password="test-pass",
        )
        user.profile.delete()
        user = User.objects.get(pk=user.pk)

        self.assertTrue(self.inline.has_add_permission(self.request, obj=user))
        self.assertEqual(self.inline.get_extra(self.request, obj=user), 1)
        self.assertEqual(self.inline.max_num, 1)
        self.assertFalse(self.inline.can_delete)




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

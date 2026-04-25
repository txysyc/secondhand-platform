from pathlib import Path

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase

from users.admin import ProfileInline
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

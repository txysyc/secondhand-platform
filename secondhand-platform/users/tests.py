from pathlib import Path

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import SESSION_KEY
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
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


class AuthenticationFlowTest(TestCase):
    """注册、登录和退出登录请求流程测试。

    覆盖 story 1.3 的认证闭环，包含用户名登录、邮箱登录、注册成功、
    表单错误恢复、next 保留和退出登录的 POST 约束。
    """

    def setUp(self):
        """准备注册服务依赖的普通用户组。"""

        self.group = Group.objects.create(name="普通用户组")

    def test_home_and_auth_pages_render(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "二手交易平台")

        response = self.client.get(reverse("users:register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "创建账号")
        self.assertContains(response, "用户名")
        self.assertContains(response, "邮箱")

        response = self.client.get(reverse("users:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户名/邮箱")

    def test_authenticated_home_does_not_render_placeholder_link(self):
        user = User.objects.create_user(
            username="homeu",
            email="homeu@example.com",
            password="StrongPass123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "账号已登录")
        self.assertNotContains(response, 'href="#"')

    def test_register_creates_user_hashes_password_and_profile(self):
        response = self.client.post(
            reverse("users:register"),
            data={
                "username": "buyer",
                "email": "Buyer@Example.com",
                "password1": "StrongPass123",
                "password2": "StrongPass123",
            },
        )

        self.assertRedirects(response, reverse("users:login"))
        user = User.objects.get(username="buyer")
        self.assertEqual(user.email, "buyer@example.com")
        self.assertNotEqual(user.password, "StrongPass123")
        self.assertTrue(user.check_password("StrongPass123"))
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertTrue(user.groups.filter(name="普通用户组").exists())

    def test_register_errors_keep_non_password_input(self):
        User.objects.create_user(
            username="taken",
            email="taken@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("users:register"),
            data={
                "username": "taken",
                "email": "New@Example.com",
                "password1": "StrongPass123",
                "password2": "DifferentPass123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "该用户名已存在")
        self.assertContains(response, 'value="taken"')
        self.assertContains(response, 'value="New@Example.com"')
        self.assertNotContains(response, "StrongPass123")

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(
            username="old",
            email="same@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("users:register"),
            data={
                "username": "fresh",
                "email": "SAME@example.com",
                "password1": "StrongPass123",
                "password2": "StrongPass123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "该邮箱已存在")
        self.assertFalse(User.objects.filter(username="fresh").exists())

    def test_login_with_username_creates_session(self):
        user = User.objects.create_user(
            username="logu",
            email="logu@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("users:login"),
            data={"username": user.username, "password": "StrongPass123"},
        )

        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL)
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_login_with_email_is_case_insensitive(self):
        user = User.objects.create_user(
            username="mailu",
            email="mailu@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("users:login"),
            data={"username": "MAILU@EXAMPLE.COM", "password": "StrongPass123"},
        )

        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL)
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_email_login_fails_when_case_insensitive_match_is_ambiguous(self):
        User.objects.create_user(
            username="maila",
            email="Case@example.com",
            password="StrongPass123",
        )
        User.objects.create_user(
            username="mailb",
            email="case@example.com",
            password="StrongPass123",
        )

        response = self.client.post(
            reverse("users:login"),
            data={"username": "CASE@example.com", "password": "StrongPass123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "请输入正确的用户名或邮箱和密码")
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_invalid_login_shows_generic_error_and_keeps_next(self):
        next_url = reverse("users:register")

        response = self.client.post(
            reverse("users:login"),
            data={
                "username": "missing@example.com",
                "password": "bad-password",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "请输入正确的用户名或邮箱和密码")
        self.assertContains(response, f'name="next" value="{next_url}"')
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_redirects_to_safe_next(self):
        user = User.objects.create_user(
            username="nextu",
            email="nextu@example.com",
            password="StrongPass123",
        )
        next_url = reverse("users:register")

        response = self.client.post(
            reverse("users:login"),
            data={
                "username": user.username,
                "password": "StrongPass123",
                "next": next_url,
            },
        )

        self.assertRedirects(response, next_url)

    def test_logout_requires_post_and_clears_session(self):
        user = User.objects.create_user(
            username="out",
            email="out@example.com",
            password="StrongPass123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("users:logout"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

        response = self.client.post(reverse("users:logout"))
        self.assertRedirects(response, settings.LOGOUT_REDIRECT_URL)
        self.assertNotIn(SESSION_KEY, self.client.session)


class ProfileEditFlowTest(TestCase):
    """公开资料编辑和受限区域访问流程测试。

    覆盖 story 1.4 的资料编辑、头像上传、当前用户隔离、缺失资料补齐、
    登录拦截和 `next` 返回路径。
    """

    def setUp(self):
        """准备资料编辑测试所需的两个普通用户。"""

        self.user = User.objects.create_user(
            username="profileu",
            email="profileu@example.com",
            password="StrongPass123",
        )
        self.other_user = User.objects.create_user(
            username="otheru",
            email="otheru@example.com",
            password="StrongPass123",
        )
        self.profile_url = reverse("users:profile")

    def test_profile_page_requires_login_and_preserves_next(self):
        response = self.client.get(self.profile_url)

        self.assertRedirects(
            response,
            f"{reverse('users:login')}?next={self.profile_url}",
        )

    def test_login_page_with_next_shows_login_required_message(self):
        response = self.client.get(reverse("users:login"), {"next": self.profile_url})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "请先登录后继续访问该页面")
        self.assertContains(response, f'name="next" value="{self.profile_url}"')

    def test_login_with_next_returns_to_profile_page(self):
        response = self.client.post(
            reverse("users:login"),
            data={
                "username": self.user.username,
                "password": "StrongPass123",
                "next": self.profile_url,
            },
        )

        self.assertRedirects(response, self.profile_url)

    def test_authenticated_user_can_open_profile_form_with_current_values(self):
        self.user.profile.nickname = "旧昵称"
        self.user.profile.bio = "旧简介"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的资料")
        self.assertContains(response, "别人看到的你")
        self.assertContains(response, "@profileu")
        self.assertContains(response, "更新资料")
        self.assertContains(response, "旧昵称")
        self.assertContains(response, "旧简介")
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "保存资料")

    def test_valid_profile_post_updates_current_user_and_redirects(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.profile_url,
            data={"nickname": "新昵称", "bio": "新的公开简介"},
            follow=True,
        )

        self.assertRedirects(response, self.profile_url)
        self.assertContains(response, "更新成功")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.nickname, "新昵称")
        self.assertEqual(self.user.profile.bio, "新的公开简介")

    def test_invalid_profile_post_keeps_existing_saved_values(self):
        self.user.profile.nickname = "原昵称"
        self.user.profile.bio = "原简介"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.post(
            self.profile_url,
            data={"nickname": "超过十个字符的用户昵称", "bio": "不会保存"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "不超过 10 字符")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.nickname, "原昵称")
        self.assertEqual(self.user.profile.bio, "原简介")

    def test_empty_nickname_returns_error_and_keeps_existing_saved_values(self):
        self.user.profile.nickname = "原昵称"
        self.user.profile.bio = "原简介"
        self.user.profile.save()
        self.client.force_login(self.user)

        response = self.client.post(
            self.profile_url,
            data={"nickname": "", "bio": "不会保存"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "这个字段是必填项。")
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.nickname, "原昵称")
        self.assertEqual(self.user.profile.bio, "原简介")

    def test_avatar_upload_updates_profile_avatar_path(self):
        self.client.force_login(self.user)
        image = SimpleUploadedFile(
            "Avatar.GIF",
            b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
            b"\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )

        with self.settings(
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.InMemoryStorage",
                },
                "staticfiles": {
                    "BACKEND": (
                        "django.contrib.staticfiles.storage.StaticFilesStorage"
                    ),
                },
            }
        ):
            response = self.client.post(
                self.profile_url,
                data={"nickname": "头像用户", "bio": "上传头像", "avatar": image},
            )

        self.assertRedirects(response, self.profile_url)
        self.user.profile.refresh_from_db()
        self.assertTrue(
            self.user.profile.avatar.name.startswith(
                f"avatars/users/{self.user.id}/"
            )
        )
        self.assertTrue(self.user.profile.avatar.name.endswith(".gif"))

    def test_profile_post_only_updates_current_user_profile(self):
        self.other_user.profile.nickname = "他人昵称"
        self.other_user.profile.bio = "他人简介"
        self.other_user.profile.save()
        self.client.force_login(self.user)

        self.client.post(
            self.profile_url,
            data={"nickname": "本人昵称", "bio": "本人简介"},
        )

        self.user.profile.refresh_from_db()
        self.other_user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.nickname, "本人昵称")
        self.assertEqual(self.other_user.profile.nickname, "他人昵称")
        self.assertEqual(self.other_user.profile.bio, "他人简介")

    def test_missing_profile_is_recreated_for_authenticated_user(self):
        self.user.profile.delete()
        self.client.force_login(self.user)

        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

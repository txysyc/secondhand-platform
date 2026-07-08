"""users 应用 pytest 测试。"""

from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import Category, Listing
from users.admin import MyUserAdmin, ProfileInline
from orders.models import Order
from users.models import Profile, User, UserAddress, avatar_upload_to
from users.signals import create_user_profile


pytestmark = pytest.mark.django_db


class TestUserModel:
    """用户模型基础行为测试。"""

    def test_auth_user_model_points_to_custom_user_model(self):
        assert django_settings.AUTH_USER_MODEL == "users.User"

    def test_get_user_model_returns_custom_user_model(self):
        assert get_user_model() is User

    def test_create_user_hashes_password(self):
        user = User.objects.create_user(
            username="hash",
            email="hash@example.com",
            password="plain-password",
        )

        assert user.password != "plain-password"
        assert user.check_password("plain-password") is True

    def test_create_superuser_keeps_admin_permissions_and_password_hash(self):
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin-password",
        )

        assert user.is_staff is True
        assert user.is_superuser is True
        assert user.check_password("admin-password") is True
        assert Profile.objects.filter(user=user).exists() is True

    def test_user_str_returns_username_label(self):
        user = User(username="张三", email="zhangsan@example.com")

        assert str(user) == "张三的账号"

    def test_username_must_not_be_shorter_than_two_chars(self):
        user = User(username="a", email="short@example.com", password="test-pass")

        with pytest.raises(ValidationError) as exc_info:
            user.full_clean()

        assert "username" in exc_info.value.message_dict

    def test_email_must_be_unique(self):
        User.objects.create_user(
            username="user1",
            email="same@example.com",
            password="test-pass",
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    username="user2",
                    email="same@example.com",
                    password="test-pass",
                )


class TestProfileModel:
    """用户资料模型和头像路径测试。"""

    def test_profile_str_returns_owner_username_label(self):
        user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="test-pass",
        )

        assert str(user.profile) == "owner的用户资料"

    def test_created_profile_uses_default_nickname(self):
        user = User.objects.create_user(
            username="nick",
            email="nick@example.com",
            password="test-pass",
        )

        assert user.profile.nickname == "初始昵称"

    def test_avatar_upload_to_uses_user_id_uuid_and_lowercase_extension(self):
        user = User.objects.create_user(
            username="avatar",
            email="avatar@example.com",
            password="test-pass",
        )

        upload_path = avatar_upload_to(user.profile, "MyAvatar.PNG")

        assert upload_path.startswith(f"avatars/users/{user.id}/")
        assert Path(upload_path).suffix == ".png"

    def test_avatar_upload_to_defaults_to_jpg_when_filename_has_no_extension(self):
        user = User.objects.create_user(
            username="noext",
            email="noext@example.com",
            password="test-pass",
        )

        upload_path = avatar_upload_to(user.profile, "avatar")

        assert upload_path.endswith(".jpg")


class TestUserAddressModel:
    """用户收货地址模型测试。"""

    def test_user_can_create_address(self):
        user = User.objects.create_user(
            username="addruser",
            email="addruser@example.com",
            password="test-pass",
        )

        address = UserAddress.objects.create(
            user=user,
            recipient_name="张三",
            phone="13800138000",
            province="广东省",
            city="深圳市",
            district="南山区",
            detail_address="科技园1号",
            is_default=True,
        )

        assert str(address) == "addruser - 张三"
        assert address.is_default is True

    def test_only_one_default_address_per_user(self):
        user = User.objects.create_user(
            username="defaddr",
            email="defaddr@example.com",
            password="test-pass",
        )
        UserAddress.objects.create(
            user=user,
            recipient_name="张三",
            phone="13800138000",
            province="广东省",
            city="深圳市",
            district="南山区",
            detail_address="科技园1号",
            is_default=True,
        )

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                UserAddress.objects.create(
                    user=user,
                    recipient_name="李四",
                    phone="13900139000",
                    province="广东省",
                    city="广州市",
                    district="天河区",
                    detail_address="体育西路1号",
                    is_default=True,
                )


class TestUserProfileSignal:
    """用户创建信号的资料自动创建测试。"""

    def test_profile_is_created_when_user_is_created(self):
        user = User.objects.create_user(
            username="signal",
            email="signal@example.com",
            password="test-pass",
        )

        assert Profile.objects.filter(user=user).exists() is True

    def test_raw_user_save_does_not_create_profile(self):
        user = User.objects.create_user(
            username="raw",
            email="raw@example.com",
            password="test-pass",
        )
        user.profile.delete()

        create_user_profile(sender=User, instance=user, created=True, raw=True)

        assert Profile.objects.filter(user=user).exists() is False

    def test_existing_profile_does_not_break_created_signal(self):
        user = User.objects.create_user(
            username="exists",
            email="exists@example.com",
            password="test-pass",
        )

        create_user_profile(sender=User, instance=user, created=True, raw=False)

        assert Profile.objects.filter(user=user).count() == 1


class TestUserAdmin:
    """用户后台注册、治理字段和访问烟雾测试。"""

    def test_user_admin_is_registered_with_profile_inline(self):
        user_admin = admin.site._registry[User]

        assert isinstance(user_admin, MyUserAdmin)
        assert ProfileInline in user_admin.inlines

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
            assert field in user_admin.list_display

        for field in ["is_active", "is_staff", "is_superuser", "groups", "created_at"]:
            assert field in user_admin.list_filter

        for field in ["id", "username", "email"]:
            assert field in user_admin.search_fields

        for field in ["created_at", "updated_at", "last_login"]:
            assert field in user_admin.readonly_fields

        permission_fields = user_admin.fieldsets[2][1]["fields"]
        assert "is_active" in permission_fields

    def test_superuser_can_open_user_admin_changelist(self, client):
        superuser = User.objects.create_superuser(
            username="useradmin",
            email="useradmin@example.com",
            password="StrongPass123",
        )
        client.force_login(superuser)

        response = client.get(reverse("admin:users_user_changelist"))

        assert response.status_code == 200

    def test_regular_user_cannot_open_user_admin_changelist(self, client):
        user = User.objects.create_user(
            username="normadm",
            email="normaladmin@example.com",
            password="StrongPass123",
        )
        client.force_login(user)

        response = client.get(reverse("admin:users_user_changelist"))

        assert response.status_code in [302, 403]


@pytest.fixture
def profile_inline_context():
    """构造后台资料 inline 及请求对象。"""

    return {
        "inline": ProfileInline(User, AdminSite()),
        "request": RequestFactory().get("/admin/users/user/1/change/"),
    }


class TestProfileInlineAdmin:
    """后台用户资料内联表单的边界行为测试。"""

    def test_profile_inline_does_not_render_extra_form_on_user_create_page(
        self,
        profile_inline_context,
    ):
        inline = profile_inline_context["inline"]
        request = profile_inline_context["request"]

        assert inline.get_extra(request, obj=None) == 0

    def test_profile_inline_does_not_allow_second_profile_when_profile_exists(
        self,
        profile_inline_context,
    ):
        inline = profile_inline_context["inline"]
        request = profile_inline_context["request"]
        user = User.objects.create_user(
            username="filled",
            email="filled@example.com",
            password="test-pass",
        )

        assert inline.has_add_permission(request, obj=user) is False
        assert inline.get_extra(request, obj=user) == 0

    def test_profile_inline_allows_one_profile_when_profile_is_missing(
        self,
        profile_inline_context,
    ):
        inline = profile_inline_context["inline"]
        request = profile_inline_context["request"]
        user = User.objects.create_user(
            username="miss",
            email="missing@example.com",
            password="test-pass",
        )
        user.profile.delete()
        user = User.objects.get(pk=user.pk)

        assert inline.has_add_permission(request, obj=user) is True
        assert inline.get_extra(request, obj=user) == 1
        assert inline.max_num == 1
        assert inline.can_delete is False


@pytest.fixture
def default_group():
    """创建注册流程依赖的默认用户组。"""

    return Group.objects.create(name="普通用户组")


class TestUsersApi:
    """用户与认证 API 测试。"""

    def test_register_creates_user_profile_and_default_group(
        self,
        api_client,
        default_group,
    ):
        response = api_client.post(
            reverse("api:auth_register"),
            data={
                "username": "buyer",
                "email": "Buyer@Example.com",
                "password": "StrongPass123",
                "password_confirm": "StrongPass123",
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.json()["username"] == "buyer"
        user = User.objects.get(username="buyer")
        assert user.email == "buyer@example.com"
        assert user.profile
        assert user.groups.filter(pk=default_group.pk).exists() is True

    def test_register_rejects_duplicate_email_and_password_mismatch(
        self,
        api_client,
        default_group,
    ):
        User.objects.create_user(
            username="taken",
            email="taken@example.com",
            password="StrongPass123",
        )

        response = api_client.post(
            reverse("api:auth_register"),
            data={
                "username": "fresh",
                "email": "taken@example.com",
                "password": "StrongPass123",
                "password_confirm": "Mismatch123",
            },
            format="json",
        )

        assert response.status_code == 400
        body = response.json()
        assert "message" in body
        assert "errors" in body

    def test_token_uses_identifier_for_username_login(self, api_client, default_group):
        user = User.objects.create_user(
            username="loginu",
            email="loginu@example.com",
            password="StrongPass123",
        )

        response = api_client.post(
            reverse("api:auth_token"),
            data={"identifier": user.username, "password": "StrongPass123"},
            format="json",
        )

        assert response.status_code == 200
        assert "access" in response.json()
        assert "refresh" in response.json()

    def test_token_uses_identifier_for_email_login(self, api_client, default_group):
        User.objects.create_user(
            username="emaillog",
            email="email-login@example.com",
            password="StrongPass123",
        )

        response = api_client.post(
            reverse("api:auth_token"),
            data={"identifier": "EMAIL-LOGIN@example.com", "password": "StrongPass123"},
            format="json",
        )

        assert response.status_code == 200
        assert "access" in response.json()

    def test_token_rejects_invalid_credentials_with_json_error(
        self,
        api_client,
        default_group,
    ):
        response = api_client.post(
            reverse("api:auth_token"),
            data={"identifier": "missing", "password": "wrong"},
            format="json",
        )

        assert response.status_code == 400
        assert "message" in response.json()
        assert "errors" in response.json()

    def test_refresh_token_returns_new_access_token(self, api_client, default_group):
        user = User.objects.create_user(
            username="refreshu",
            email="refreshu@example.com",
            password="StrongPass123",
        )
        refresh = RefreshToken.for_user(user)

        response = api_client.post(
            reverse("api:auth_token_refresh"),
            data={"refresh": str(refresh)},
            format="json",
        )

        assert response.status_code == 200
        assert "access" in response.json()

    def test_me_get_returns_current_user_profile(
        self,
        api_client,
        auth_headers,
        default_group,
    ):
        user = User.objects.create_user(
            username="profileu",
            email="profileu@example.com",
            password="StrongPass123",
        )
        user.profile.nickname = "我的昵称"
        user.profile.bio = "公开简介"
        user.profile.save()

        response = api_client.get(
            reverse("api:users_me"),
            **auth_headers(user),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "profileu"
        assert body["profile"]["nickname"] == "我的昵称"
        assert body["profile"]["bio"] == "公开简介"

    def test_me_patch_updates_profile_and_avatar(
        self,
        api_client,
        auth_headers,
        png_image,
        settings,
        default_group,
    ):
        user = User.objects.create_user(
            username="updateu",
            email="updateu@example.com",
            password="StrongPass123",
        )
        settings.STORAGES = {
            "default": {
                "BACKEND": "django.core.files.storage.InMemoryStorage",
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }

        response = api_client.patch(
            reverse("api:users_me"),
            data={"nickname": "新昵称", "bio": "新简介", "avatar": png_image("avatar.png")},
            format="multipart",
            **auth_headers(user),
        )

        assert response.status_code == 200
        user.profile.refresh_from_db()
        assert user.profile.nickname == "新昵称"
        assert user.profile.bio == "新简介"

    def test_public_user_profile_includes_active_listings(self, api_client, default_group):
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

        response = api_client.get(reverse("api:users_public", kwargs={"user_id": seller.id}))

        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "seller"
        assert body["listings"][0]["title"] == "公开商品"
        assert body["listings"][0]["category_name"] == "公开分类"

    def test_public_user_profile_returns_404_for_missing_user(
        self,
        api_client,
        default_group,
    ):
        response = api_client.get(reverse("api:users_public", kwargs={"user_id": 99999}))

        assert response.status_code == 404

    def test_address_api_requires_login(self, api_client):
        response = api_client.get(reverse("api:users_me_addresses"))

        assert response.status_code == 401

    def test_create_first_address_auto_default_and_trims_text(
        self,
        api_client,
        auth_headers,
    ):
        user = User.objects.create_user(
            username="addrapi",
            email="addrapi@example.com",
            password="StrongPass123",
        )

        response = api_client.post(
            reverse("api:users_me_addresses"),
            data={
                "recipient_name": " 张三 ",
                "phone": " 13800138000 ",
                "province": " 广东省 ",
                "city": " 深圳市 ",
                "district": " 南山区 ",
                "detail_address": " 科技园1号 ",
            },
            format="json",
            **auth_headers(user),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["recipient_name"] == "张三"
        assert body["phone"] == "13800138000"
        assert body["is_default"] is True

    def test_address_api_crud_and_owner_scope(self, api_client, auth_headers):
        user = User.objects.create_user(
            username="addrowner",
            email="addrowner@example.com",
            password="StrongPass123",
        )
        other = User.objects.create_user(
            username="addrother",
            email="addrother@example.com",
            password="StrongPass123",
        )
        address = UserAddress.objects.create(
            user=user,
            recipient_name="张三",
            phone="13800138000",
            province="广东省",
            city="深圳市",
            district="南山区",
            detail_address="科技园1号",
            is_default=True,
        )

        other_response = api_client.get(
            reverse("api:users_me_address_detail", kwargs={"pk": address.id}),
            **auth_headers(other),
        )
        patch_response = api_client.patch(
            reverse("api:users_me_address_detail", kwargs={"pk": address.id}),
            data={"detail_address": "软件园2号"},
            format="json",
            **auth_headers(user),
        )
        list_response = api_client.get(
            reverse("api:users_me_addresses"),
            **auth_headers(user),
        )
        delete_response = api_client.delete(
            reverse("api:users_me_address_detail", kwargs={"pk": address.id}),
            **auth_headers(user),
        )

        assert other_response.status_code == 404
        assert patch_response.status_code == 200
        assert patch_response.json()["detail_address"] == "软件园2号"
        assert list_response.status_code == 200
        assert list_response.json()[0]["id"] == address.id
        assert delete_response.status_code == 204
        assert UserAddress.objects.filter(pk=address.id).exists() is False

    def test_address_api_rejects_blank_required_fields(self, api_client, auth_headers):
        user = User.objects.create_user(
            username="blankaddr",
            email="blankaddr@example.com",
            password="StrongPass123",
        )

        response = api_client.post(
            reverse("api:users_me_addresses"),
            data={
                "recipient_name": " ",
                "phone": "13800138000",
                "province": "广东省",
                "city": "深圳市",
                "district": "南山区",
                "detail_address": "科技园1号",
            },
            format="json",
            **auth_headers(user),
        )

        assert response.status_code == 400
        assert "recipient_name" in response.json()["errors"]

    def test_set_default_address_unsets_old_default(self, api_client, auth_headers):
        user = User.objects.create_user(
            username="setdef",
            email="setdef@example.com",
            password="StrongPass123",
        )
        old_default = UserAddress.objects.create(
            user=user,
            recipient_name="张三",
            phone="13800138000",
            province="广东省",
            city="深圳市",
            district="南山区",
            detail_address="科技园1号",
            is_default=True,
        )
        new_default = UserAddress.objects.create(
            user=user,
            recipient_name="李四",
            phone="13900139000",
            province="广东省",
            city="广州市",
            district="天河区",
            detail_address="体育西路1号",
        )

        response = api_client.post(
            reverse("api:users_me_address_set_default", kwargs={"pk": new_default.id}),
            **auth_headers(user),
        )

        assert response.status_code == 200
        old_default.refresh_from_db()
        new_default.refresh_from_db()
        assert old_default.is_default is False
        assert new_default.is_default is True

    def test_delete_address_does_not_affect_order_snapshot(self):
        buyer = User.objects.create_user(
            username="snapbuyer",
            email="snapbuyer@example.com",
            password="StrongPass123",
        )
        seller = User.objects.create_user(
            username="snapseller",
            email="snapseller@example.com",
            password="StrongPass123",
        )
        category = Category.objects.create(name="快照分类")
        listing = Listing.objects.create(
            owner=seller,
            category=category,
            title="快照商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="商品描述",
        )
        address = UserAddress.objects.create(
            user=buyer,
            recipient_name="张三",
            phone="13800138000",
            province="广东省",
            city="深圳市",
            district="南山区",
            detail_address="科技园1号",
        )
        order = Order.objects.create(
            buyer=buyer,
            seller=seller,
            listing=listing,
            buyer_display_name=buyer.username,
            seller_display_name=seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            payment_deadline=timezone.now(),
            shipping_recipient_name=address.recipient_name,
            shipping_phone=address.phone,
            shipping_province=address.province,
            shipping_city=address.city,
            shipping_district=address.district,
            shipping_detail_address=address.detail_address,
        )

        address.delete()
        order.refresh_from_db()

        assert order.shipping_recipient_name == "张三"
        assert order.shipping_detail_address == "科技园1号"

"""users 应用 pytest 测试。"""

from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
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

@pytest.fixture
def default_group():
    """创建注册流程依赖的默认用户组。"""

    return Group.objects.create(name="普通用户组")


class TestUsersApi:
    """用户与认证 API 测试。"""

    @pytest.fixture(autouse=True)
    def _clear_throttle_cache(self):
        """隔离认证限流计数，避免其他 API 用例污染本模块断言。"""

        cache.clear()
        yield
        cache.clear()

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

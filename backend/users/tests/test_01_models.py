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



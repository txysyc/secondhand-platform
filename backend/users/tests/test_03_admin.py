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



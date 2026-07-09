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



from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import Category, Listing, ListingImage
from orders.admin import OrderAdmin
from orders.models import Order
from orders.selectors import get_buyer_orders, get_seller_orders
from orders.services import (
    cancel_expired_pending_orders,
    auto_complete_eligible_physical_order,
    auto_complete_eligible_virtual_order,
    confirm_order_delivery,
    confirm_order_receipt,
    create_order,
    mark_due_physical_orders_signed,
    pay_order,
)
from orders import tasks as order_tasks
from users.models import UserAddress

User = get_user_model()


pytestmark = pytest.mark.django_db

class TestOrderAdmin:
    """订单后台注册、治理字段和访问烟雾测试。"""

    def test_order_admin_is_registered(self):
        assert isinstance(admin.site._registry[Order], OrderAdmin)

    def test_order_admin_exposes_required_columns_filters_search_and_readonly_fields(self):
        order_admin = admin.site._registry[Order]

        expected_display = [
            "id",
            "buyer",
            "seller",
            "listing",
            "status",
            "order_price",
            "payment_deadline",
            "paid_at",
            "shipped_at",
            "signed_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]
        for field in expected_display:
            assert field in order_admin.list_display
            assert field in order_admin.readonly_fields
        assert "logistics_signed_due_at" in order_admin.readonly_fields

        for field in ["status", "buyer", "seller", "created_at", "updated_at"]:
            assert field in order_admin.list_filter

        for field in [
            "listing_title_snapshot",
            "buyer_display_name",
            "seller_display_name",
            "buyer__username",
            "seller__username",
        ]:
            assert field in order_admin.search_fields

        assert order_admin.list_select_related == ["buyer", "seller", "listing"]

    def test_superuser_can_open_order_admin_changelist(self, client):
        superuser = User.objects.create_superuser(
            username="orderadmin",
            email="orderadmin@example.com",
            password="StrongPass123",
        )
        client.force_login(superuser)

        response = client.get(reverse("admin:orders_order_changelist"))

        assert response.status_code == 200

    def test_regular_user_cannot_open_order_admin_changelist(self, client):
        user = User.objects.create_user(
            username="ordnorm",
            email="ordernormal@example.com",
            password="StrongPass123",
        )
        client.force_login(user)

        response = client.get(reverse("admin:orders_order_changelist"))

        assert response.status_code in [302, 403]



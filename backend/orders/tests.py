from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

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

User = get_user_model()


class OrderModelTest(TestCase):
    """Order 模型基础行为测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def test_order_default_status_is_pending_payment(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_order_str_representation(self):
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        self.assertIn("测试商品", str(order) if hasattr(order, '__str__') else "测试商品")

    def test_order_set_null_on_buyer_delete(self):
        temp_buyer = User.objects.create_user(
            username="临时买家", email="temp@test.com", password="testpass123"
        )
        order = Order.objects.create(
            buyer=temp_buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="临时买家",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        temp_buyer.delete()
        order.refresh_from_db()
        self.assertIsNone(order.buyer)
        self.assertEqual(order.buyer_display_name, "临时买家")


class OrderAdminTest(TestCase):
    """订单后台注册、治理字段和访问烟雾测试。"""

    def test_order_admin_is_registered(self):
        self.assertIsInstance(admin.site._registry[Order], OrderAdmin)

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
            self.assertIn(field, order_admin.list_display)
            self.assertIn(field, order_admin.readonly_fields)
        self.assertIn("logistics_signed_due_at", order_admin.readonly_fields)

        for field in ["status", "buyer", "seller", "created_at", "updated_at"]:
            self.assertIn(field, order_admin.list_filter)

        for field in [
            "listing_title_snapshot",
            "buyer_display_name",
            "seller_display_name",
            "buyer__username",
            "seller__username",
        ]:
            self.assertIn(field, order_admin.search_fields)

        self.assertEqual(order_admin.list_select_related, ["buyer", "seller", "listing"])

    def test_superuser_can_open_order_admin_changelist(self):
        superuser = User.objects.create_superuser(
            username="orderadmin",
            email="orderadmin@example.com",
            password="StrongPass123",
        )
        self.client.force_login(superuser)

        response = self.client.get(reverse("admin:orders_order_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_open_order_admin_changelist(self):
        user = User.objects.create_user(
            username="ordnorm",
            email="ordernormal@example.com",
            password="StrongPass123",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:orders_order_changelist"))

        self.assertIn(response.status_code, [302, 403])


class CreateOrderServiceTest(TestCase):
    """create_order 服务层测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")

    def _create_active_listing(self, **kwargs):
        defaults = {
            "owner": self.seller,
            "category": self.category,
            "title": "测试商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("199.00"),
            "description": "测试描述",
        }
        defaults.update(kwargs)
        return Listing.objects.create(**defaults)

    def test_create_order_success(self):
        listing = self._create_active_listing()
        order = create_order(self.buyer, listing)

        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order.buyer, self.buyer)
        self.assertEqual(order.seller, self.seller)
        self.assertEqual(order.listing, listing)
        self.assertEqual(order.order_price, Decimal("199.00"))
        self.assertEqual(order.listing_title_snapshot, "测试商品")

    def test_create_order_captures_first_listing_image_snapshot(self):
        listing = self._create_active_listing()
        ListingImage.objects.create(
            listing=listing,
            image="listings/later.png",
            sort_order=2,
        )
        first_image = ListingImage.objects.create(
            listing=listing,
            image="listings/first.png",
            sort_order=1,
        )

        order = create_order(self.buyer, listing)

        self.assertEqual(order.listing_image_snapshot, first_image.image.url)

    def test_create_order_listing_status_unchanged(self):
        listing = self._create_active_listing()
        create_order(self.buyer, listing)

        listing.refresh_from_db()
        self.assertEqual(listing.status, Listing.Status.ACTIVE)

    def test_payment_deadline_is_15_minutes_from_now(self):
        listing = self._create_active_listing()
        before = timezone.now()
        order = create_order(self.buyer, listing)
        after = timezone.now()

        expected_min = before + timedelta(minutes=15)
        expected_max = after + timedelta(minutes=15)
        self.assertGreaterEqual(order.payment_deadline, expected_min)
        self.assertLessEqual(order.payment_deadline, expected_max)

    def test_buyer_cannot_purchase_own_listing(self):
        listing = self._create_active_listing(owner=self.buyer)

        with self.assertRaises(PermissionDenied):
            create_order(self.buyer, listing)

    def test_cannot_order_non_active_listing(self):
        for status in [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]:
            listing = self._create_active_listing(status=status)
            with self.assertRaises(ValidationError):
                create_order(self.buyer, listing)

    def test_rejects_duplicate_unexpired_pending_order_for_same_listing(self):
        listing = self._create_active_listing()
        another_buyer = User.objects.create_user(
            username="买家C", email="buyerc@test.com", password="testpass123"
        )
        order1 = create_order(self.buyer, listing)

        with self.assertRaises(ValidationError):
            create_order(another_buyer, listing)

        self.assertEqual(order1.status, Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(
            Order.objects.filter(
                listing=listing, status=Order.OrderStatus.PENDING_PAYMENT
            ).count(),
            1,
        )

    def test_expired_pending_order_does_not_block_new_order(self):
        listing = self._create_active_listing()
        Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=self.buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now() - timedelta(minutes=1),
        )
        another_buyer = User.objects.create_user(
            username="买家C", email="buyerc@test.com", password="testpass123"
        )

        order = create_order(another_buyer, listing)

        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_snapshot_fields_captured_at_creation(self):
        listing = self._create_active_listing(title="原始标题", price=Decimal("50.00"))
        order = create_order(self.buyer, listing)

        listing.title = "修改后标题"
        listing.price = Decimal("999.00")
        listing.save()

        order.refresh_from_db()
        self.assertEqual(order.listing_title_snapshot, "原始标题")
        self.assertEqual(order.order_price, Decimal("50.00"))

    def test_display_name_uses_nickname(self):
        self.buyer.profile.nickname = "买家昵称"
        self.buyer.profile.save()
        self.seller.profile.nickname = "卖家昵称"
        self.seller.profile.save()

        listing = self._create_active_listing()
        order = create_order(self.buyer, listing)

        self.assertEqual(order.buyer_display_name, "买家昵称")
        self.assertEqual(order.seller_display_name, "卖家昵称")


class PayOrderServiceTest(TransactionTestCase):
    """pay_order 服务层测试。使用 TransactionTestCase 以正确测试 select_for_update 行为。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="路人C", email="other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="数码产品")
        self.listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_pending_order(self, buyer=None, listing=None, deadline_minutes=15):
        buyer = buyer or self.buyer
        listing = listing or self.listing
        return Order.objects.create(
            buyer=buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline=timezone.now() + timedelta(minutes=deadline_minutes),
        )

    def test_buyer_can_pay_pending_order(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertIsNotNone(order.paid_at)

    def test_payment_sets_listing_to_reserved(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.RESERVED)

    def test_payment_does_not_set_completed(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)

    def test_seller_cannot_pay(self):
        order = self._create_pending_order()
        with self.assertRaises(PermissionDenied):
            pay_order(self.seller, order.pk)

    def test_other_user_cannot_pay(self):
        order = self._create_pending_order()
        with self.assertRaises(PermissionDenied):
            pay_order(self.other_user, order.pk)

    def test_expired_order_payment_fails_and_cancels(self):
        order = self._create_pending_order(deadline_minutes=-1)
        with self.assertRaises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        self.assertIn("超时", str(ctx.exception))

    def test_non_active_listing_payment_fails(self):
        self.listing.status = Listing.Status.RESERVED
        self.listing.save()
        order = self._create_pending_order()
        with self.assertRaises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        self.assertIn("不可购买", str(ctx.exception))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_concurrent_orders_only_one_succeeds(self):
        buyer2 = User.objects.create_user(
            username="买家D", email="buyerd@test.com", password="testpass123"
        )
        order1 = self._create_pending_order(buyer=self.buyer)
        order2 = self._create_pending_order(buyer=buyer2)

        pay_order(self.buyer, order1.pk)

        with self.assertRaises(ValidationError):
            pay_order(buyer2, order2.pk)

        order1.refresh_from_db()
        order2.refresh_from_db()
        self.listing.refresh_from_db()
        self.assertEqual(order1.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertNotEqual(order2.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertEqual(self.listing.status, Listing.Status.RESERVED)

    def test_listing_none_payment_fails(self):
        order = self._create_pending_order()
        order.listing = None
        order.save()
        with self.assertRaises(ValidationError) as ctx:
            pay_order(self.buyer, order.pk)
        self.assertIn("商品不存在", str(ctx.exception))

    def test_already_paid_order_cannot_pay_again(self):
        order = self._create_pending_order()
        pay_order(self.buyer, order.pk)
        with self.assertRaises(ValidationError):
            pay_order(self.buyer, order.pk)


class ConfirmOrderDeliveryServiceTest(TransactionTestCase):
    """confirm_order_delivery 服务层测试。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="交付买家", email="delivery-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="交付卖家", email="delivery-seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="交付路人", email="delivery-other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="交付分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="交付商品",
            item_type=item_type,
            status=status,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_order(self, status=Order.OrderStatus.AWAITING_SHIPMENT, listing=None):
        listing = listing or self._create_listing()
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            buyer_display_name=self.buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=listing.title,
            order_price=listing.price,
            status=status,
            payment_deadline=timezone.now() + timedelta(minutes=15),
            paid_at=timezone.now(),
        )

    def test_seller_can_confirm_physical_delivery(self):
        order = self._create_order()
        before = timezone.now()
        confirm_order_delivery(self.seller, order.pk)
        after = timezone.now()
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertIsNotNone(order.shipped_at)
        self.assertEqual(order.listing.status, Listing.Status.RESERVED)
        self.assertIsNotNone(order.logistics_signed_due_at)
        self.assertGreaterEqual(order.logistics_signed_due_at, order.shipped_at + timedelta(days=1))
        self.assertLessEqual(order.logistics_signed_due_at, order.shipped_at + timedelta(days=5))
        self.assertGreaterEqual(order.shipped_at, before)

    def test_virtual_delivery_does_not_create_logistics_due_at(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertIsNotNone(order.shipped_at)
        self.assertIsNone(order.logistics_signed_due_at)

    def test_buyer_and_other_user_cannot_confirm_delivery(self):
        for user in [self.buyer, self.other_user]:
            order = self._create_order()
            with self.assertRaises(PermissionDenied):
                confirm_order_delivery(user, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
            self.assertIsNone(order.shipped_at)

    def test_invalid_statuses_cannot_confirm_delivery(self):
        invalid_statuses = [
            Order.OrderStatus.PENDING_PAYMENT,
            Order.OrderStatus.CANCELLED,
            Order.OrderStatus.AWAITING_RECEIPT,
            Order.OrderStatus.SIGNED,
            Order.OrderStatus.COMPLETED,
        ]
        for status in invalid_statuses:
            order = self._create_order(status=status)
            with self.assertRaises(ValidationError):
                confirm_order_delivery(self.seller, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, status)
            self.assertIsNone(order.shipped_at)
            self.assertIsNone(order.logistics_signed_due_at)

    def test_listing_none_cannot_confirm_delivery(self):
        order = self._create_order()
        order.listing = None
        order.save(update_fields=["listing"])
        with self.assertRaises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertIsNone(order.shipped_at)

    def test_non_reserved_listing_cannot_confirm_delivery(self):
        listing = self._create_listing(status=Listing.Status.ACTIVE)
        order = self._create_order(listing=listing)
        with self.assertRaises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)

    def test_repeated_delivery_confirmation_is_idempotently_rejected(self):
        order = self._create_order()
        confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        shipped_at = order.shipped_at
        logistics_signed_due_at = order.logistics_signed_due_at
        with self.assertRaises(ValidationError):
            confirm_order_delivery(self.seller, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(order.shipped_at, shipped_at)
        self.assertEqual(order.logistics_signed_due_at, logistics_signed_due_at)


class ConfirmOrderReceiptServiceTest(TransactionTestCase):
    """confirm_order_receipt 服务层测试。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="收货买家", email="receipt-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="收货卖家", email="receipt-seller@test.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="收货路人", email="receipt-other@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="收货分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="收货商品",
            item_type=item_type,
            status=status,
            price=Decimal("109.00"),
            description="测试描述",
        )

    def _create_order(self, status=Order.OrderStatus.AWAITING_RECEIPT, listing=None, **kwargs):
        listing = listing or self._create_listing()
        defaults = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": listing.title,
            "order_price": listing.price,
            "status": status,
            "payment_deadline": timezone.now() + timedelta(minutes=15),
            "paid_at": timezone.now() - timedelta(days=1),
            "shipped_at": timezone.now() - timedelta(hours=2),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_buyer_can_complete_virtual_awaiting_receipt_order(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(listing.status, Listing.Status.SOLD)

    def test_buyer_can_complete_physical_awaiting_receipt_order(self):
        order = self._create_order(status=Order.OrderStatus.AWAITING_RECEIPT)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.listing.status, Listing.Status.SOLD)

    def test_buyer_can_complete_physical_signed_order(self):
        order = self._create_order(status=Order.OrderStatus.SIGNED, signed_at=timezone.now())
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.listing.status, Listing.Status.SOLD)

    def test_seller_and_other_user_cannot_confirm_receipt(self):
        for user in [self.seller, self.other_user]:
            order = self._create_order()
            with self.assertRaises(PermissionDenied):
                confirm_order_receipt(user, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
            self.assertIsNone(order.completed_at)

    def test_invalid_statuses_cannot_confirm_receipt(self):
        for status in [
            Order.OrderStatus.PENDING_PAYMENT,
            Order.OrderStatus.CANCELLED,
            Order.OrderStatus.AWAITING_SHIPMENT,
            Order.OrderStatus.COMPLETED,
        ]:
            order = self._create_order(status=status)
            with self.assertRaises(ValidationError):
                confirm_order_receipt(self.buyer, order.pk)
            order.refresh_from_db()
            self.assertEqual(order.status, status)
            self.assertIsNone(order.completed_at)

    def test_listing_none_cannot_confirm_receipt(self):
        order = self._create_order()
        order.listing = None
        order.save(update_fields=["listing"])
        with self.assertRaises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertIsNone(order.completed_at)

    def test_non_reserved_listing_cannot_confirm_receipt(self):
        listing = self._create_listing(status=Listing.Status.ACTIVE)
        order = self._create_order(listing=listing)
        with self.assertRaises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)

    def test_repeated_receipt_confirmation_does_not_override_completed_at(self):
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(listing=listing)
        confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        completed_at = order.completed_at
        with self.assertRaises(ValidationError):
            confirm_order_receipt(self.buyer, order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertEqual(order.completed_at, completed_at)


class DeliveryAndReceiptTaskServiceTest(TransactionTestCase):
    """模拟签收和自动完成服务测试。"""

    def setUp(self):
        self.buyer = User.objects.create_user(
            username="任务买家", email="task-buyer@test.com", password="testpass123"
        )
        self.seller = User.objects.create_user(
            username="任务卖家", email="task-seller@test.com", password="testpass123"
        )
        self.category = Category.objects.create(name="任务分类")

    def _create_listing(self, item_type=Listing.ItemType.PHYSICAL, status=Listing.Status.RESERVED):
        return Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="任务商品",
            item_type=item_type,
            status=status,
            price=Decimal("119.00"),
            description="测试描述",
        )

    def _create_order(self, listing=None, status=Order.OrderStatus.AWAITING_RECEIPT, **kwargs):
        listing = listing or self._create_listing()
        defaults = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": listing.title,
            "order_price": listing.price,
            "status": status,
            "payment_deadline": timezone.now() + timedelta(minutes=15),
            "paid_at": timezone.now() - timedelta(days=2),
            "shipped_at": timezone.now() - timedelta(days=2),
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    def test_mark_due_physical_orders_signed_only_updates_due_physical_orders(self):
        now = timezone.now()
        due = self._create_order(logistics_signed_due_at=now - timedelta(minutes=1))
        not_due = self._create_order(logistics_signed_due_at=now + timedelta(days=1))
        virtual = self._create_order(
            listing=self._create_listing(item_type=Listing.ItemType.VIRTUAL),
            logistics_signed_due_at=now - timedelta(minutes=1),
        )
        count = mark_due_physical_orders_signed(now=now)
        self.assertEqual(count, 1)
        due.refresh_from_db()
        not_due.refresh_from_db()
        virtual.refresh_from_db()
        self.assertEqual(due.status, Order.OrderStatus.SIGNED)
        self.assertIsNotNone(due.signed_at)
        self.assertEqual(not_due.status, Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(virtual.status, Order.OrderStatus.AWAITING_RECEIPT)
        due.listing.refresh_from_db()
        self.assertEqual(due.listing.status, Listing.Status.RESERVED)

    def test_mark_due_physical_orders_signed_is_idempotent(self):
        now = timezone.now()
        order = self._create_order(logistics_signed_due_at=now - timedelta(minutes=1))
        first = mark_due_physical_orders_signed(now=now)
        order.refresh_from_db()
        signed_at = order.signed_at
        second = mark_due_physical_orders_signed(now=now + timedelta(minutes=5))
        order.refresh_from_db()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(order.signed_at, signed_at)

    def test_auto_complete_physical_signed_after_three_days(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=3, minutes=1),
        )
        count = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        order.listing.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.listing.status, Listing.Status.SOLD)

    def test_auto_complete_physical_not_before_three_days(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=2, hours=23),
        )
        count = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(order.status, Order.OrderStatus.SIGNED)

    def test_auto_complete_virtual_after_seven_days(self):
        now = timezone.now()
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(
            listing=listing,
            shipped_at=now - timedelta(days=7, minutes=1),
        )
        count = auto_complete_eligible_virtual_order(now=now)
        order.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(order.status, Order.OrderStatus.COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(listing.status, Listing.Status.SOLD)

    def test_auto_complete_virtual_not_before_seven_days(self):
        now = timezone.now()
        listing = self._create_listing(item_type=Listing.ItemType.VIRTUAL)
        order = self._create_order(
            listing=listing,
            shipped_at=now - timedelta(days=6, hours=23),
        )
        count = auto_complete_eligible_virtual_order(now=now)
        order.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_RECEIPT)

    def test_auto_complete_is_idempotent(self):
        now = timezone.now()
        order = self._create_order(
            status=Order.OrderStatus.SIGNED,
            signed_at=now - timedelta(days=3, minutes=1),
        )
        first = auto_complete_eligible_physical_order(now=now)
        order.refresh_from_db()
        completed_at = order.completed_at
        second = auto_complete_eligible_physical_order(now=now + timedelta(minutes=5))
        order.refresh_from_db()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(order.completed_at, completed_at)

    def test_tasks_return_processed_counts(self):
        with patch.object(order_tasks, "mark_due_physical_orders_signed", return_value=2):
            self.assertEqual(order_tasks.mark_due_physical_orders_signed_task(), 2)
        with patch.object(order_tasks, "auto_complete_eligible_physical_order", return_value=1), patch.object(
            order_tasks, "auto_complete_eligible_virtual_order", return_value=3
        ):
            self.assertEqual(order_tasks.auto_complete_eligible_orders_task(), 4)


class CancelExpiredOrdersTest(TestCase):
    """cancel_expired_pending_orders 服务层测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("99.00"),
            description="测试描述",
        )

    def _create_order(self, status, deadline_minutes):
        return Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=self.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("99.00"),
            status=status,
            payment_deadline=timezone.now() + timedelta(minutes=deadline_minutes),
        )

    def test_cancels_expired_pending_orders(self):
        order = self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)
        self.assertIsNotNone(order.cancelled_at)

    def test_does_not_cancel_non_expired_orders(self):
        order = self._create_order(Order.OrderStatus.PENDING_PAYMENT, 10)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 0)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.PENDING_PAYMENT)

    def test_does_not_modify_paid_orders(self):
        order = self._create_order(Order.OrderStatus.AWAITING_SHIPMENT, -5)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 0)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.AWAITING_SHIPMENT)

    def test_does_not_modify_already_cancelled_orders(self):
        order = self._create_order(Order.OrderStatus.CANCELLED, -5)
        count = cancel_expired_pending_orders()
        self.assertEqual(count, 0)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.OrderStatus.CANCELLED)

    def test_idempotent_repeated_execution(self):
        self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        count1 = cancel_expired_pending_orders()
        count2 = cancel_expired_pending_orders()
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 0)

    def test_does_not_modify_listing_status(self):
        self._create_order(Order.OrderStatus.PENDING_PAYMENT, -5)
        cancel_expired_pending_orders()
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.ACTIVE)




class OrdersApiTests(APITestCase):
    """P5 订单 API 测试。"""

    def setUp(self):
        self.client = APIClient()
        self.buyer = User.objects.create_user(
            username="obuyer",
            email="order_buyer@example.com",
            password="StrongPass123",
        )
        self.seller = User.objects.create_user(
            username="oseller",
            email="order_seller@example.com",
            password="StrongPass123",
        )
        self.other = User.objects.create_user(
            username="oother",
            email="order_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="订单分类")
        self.listing = self.create_listing()

    def auth_headers(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def create_listing(self, **overrides):
        data = {
            "owner": self.seller,
            "category": self.category,
            "title": "订单商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("199.00"),
            "condition": Listing.Condition.GOOD,
            "description": "订单商品描述",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def create_order(self, **overrides):
        data = {
            "buyer": self.buyer,
            "seller": self.seller,
            "listing": self.listing,
            "buyer_display_name": self.buyer.username,
            "seller_display_name": self.seller.username,
            "listing_title_snapshot": self.listing.title,
            "order_price": self.listing.price,
            "status": Order.OrderStatus.PENDING_PAYMENT,
            "payment_deadline": timezone.now() + timedelta(minutes=15),
        }
        data.update(overrides)
        return Order.objects.create(**data)

    def test_create_order_requires_login(self):
        response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_buyer_can_create_order_for_active_listing(self):
        response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(body["viewer_role"], "buyer")
        self.assertEqual(body["available_actions"], ["pay"])
        self.assertIn("listing_image_snapshot", body)
        self.assertTrue(
            Order.objects.filter(
                pk=body["id"],
                buyer=self.buyer,
                seller=self.seller,
                listing=self.listing,
            ).exists()
        )

    def test_create_order_rejects_self_purchase_and_non_active_listing(self):
        self_purchase_response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
            **self.auth_headers(self.seller),
        )
        withdrawn = self.create_listing(status=Listing.Status.WITHDRAWN)
        withdrawn_response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": withdrawn.id}),
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(self_purchase_response.status_code, 403)
        self.assertEqual(self_purchase_response.json()["message"], "用户不能购买自己发布的商品")
        self.assertEqual(withdrawn_response.status_code, 400)
        self.assertEqual(withdrawn_response.json()["message"], "该商品不能购买")

    def test_create_order_rejects_duplicate_unexpired_pending_order(self):
        self.create_order()

        response = self.client.post(
            reverse("api:orders_create", kwargs={"listing_id": self.listing.id}),
            format="json",
            **self.auth_headers(self.other),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "该商品已有待支付订单，请稍后再试")

    def test_buyer_and_seller_lists_only_return_related_orders(self):
        buyer_order = self.create_order()
        seller_order = self.create_order(
            buyer=self.other,
            buyer_display_name=self.other.username,
        )
        unrelated_seller = User.objects.create_user(
            username="other_sell",
            email="unrelated_seller@example.com",
            password="StrongPass123",
        )
        unrelated_listing = self.create_listing(owner=unrelated_seller)
        self.create_order(
            buyer=self.other,
            seller=unrelated_seller,
            listing=unrelated_listing,
            seller_display_name=unrelated_seller.username,
        )

        buyer_response = self.client.get(
            reverse("api:orders_buyer"),
            **self.auth_headers(self.buyer),
        )
        seller_response = self.client.get(
            reverse("api:orders_seller"),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(buyer_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in buyer_response.json()["results"]],
            [buyer_order.id],
        )
        self.assertEqual(seller_response.status_code, 200)
        self.assertEqual(
            sorted(item["id"] for item in seller_response.json()["results"]),
            sorted([buyer_order.id, seller_order.id]),
        )

    def test_order_detail_requires_participant_and_exposes_display_fields(self):
        order = self.create_order()

        other_response = self.client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.other),
        )
        buyer_response = self.client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(other_response.status_code, 403)
        self.assertEqual(buyer_response.status_code, 200)
        body = buyer_response.json()
        self.assertEqual(body["viewer_role"], "buyer")
        self.assertFalse(body["is_expired"])
        self.assertEqual(body["available_actions"], ["pay"])
        self.assertEqual(body["listing_title_snapshot"], "订单商品")
        self.assertIn("images", body["listing"])

    def test_expired_order_detail_hides_pay_action(self):
        order = self.create_order(payment_deadline=timezone.now() - timedelta(minutes=1))

        response = self.client.get(
            reverse("api:orders_detail", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_expired"])
        self.assertEqual(response.json()["available_actions"], [])

    def test_buyer_can_pay_and_repeat_or_expired_payment_fail(self):
        order = self.create_order()

        paid_response = self.client.post(
            reverse("api:orders_pay", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        repeat_response = self.client.post(
            reverse("api:orders_pay", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        expired_listing = self.create_listing(title="过期支付商品")
        expired_order = self.create_order(
            listing=expired_listing,
            listing_title_snapshot=expired_listing.title,
            payment_deadline=timezone.now() - timedelta(minutes=1),
        )
        expired_response = self.client.post(
            reverse("api:orders_pay", kwargs={"pk": expired_order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(paid_response.status_code, 200)
        self.assertEqual(paid_response.json()["status"], Order.OrderStatus.AWAITING_SHIPMENT)
        self.assertEqual(paid_response.json()["available_actions"], [])
        self.assertEqual(repeat_response.status_code, 400)
        self.assertEqual(repeat_response.json()["message"], "该订单已支付或已取消，请勿重复购买")
        self.assertEqual(expired_response.status_code, 400)
        self.assertEqual(expired_response.json()["message"], "订单已超时，系统已自动取消")

    def test_seller_can_confirm_delivery_once(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            paid_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])

        response = self.client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )
        repeat_response = self.client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], Order.OrderStatus.AWAITING_RECEIPT)
        self.assertEqual(response.json()["viewer_role"], "seller")
        self.assertEqual(response.json()["available_actions"], [])
        self.assertEqual(repeat_response.status_code, 400)
        self.assertEqual(repeat_response.json()["message"], "订单不是待发货状态")

    def test_wrong_user_cannot_confirm_delivery_or_receipt(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            paid_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])

        buyer_delivery_response = self.client.post(
            reverse("api:orders_confirm_delivery", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        seller_receipt_response = self.client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": order.id}),
            **self.auth_headers(self.seller),
        )

        self.assertEqual(buyer_delivery_response.status_code, 403)
        self.assertEqual(seller_receipt_response.status_code, 403)

    def test_buyer_can_confirm_receipt_and_invalid_status_fails(self):
        order = self.create_order(
            status=Order.OrderStatus.AWAITING_RECEIPT,
            paid_at=timezone.now() - timedelta(days=1),
            shipped_at=timezone.now(),
        )
        self.listing.status = Listing.Status.RESERVED
        self.listing.save(update_fields=["status"])
        pending_order = self.create_order()

        response = self.client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": order.id}),
            **self.auth_headers(self.buyer),
        )
        invalid_response = self.client.post(
            reverse("api:orders_confirm_receipt", kwargs={"pk": pending_order.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], Order.OrderStatus.COMPLETED)
        self.assertEqual(response.json()["available_actions"], [])
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, Listing.Status.SOLD)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_response.json()["message"], "实体商品订单不能确认收货")

    def test_api_does_not_change_celery_task_behavior(self):
        with patch.object(order_tasks, "cancel_expired_pending_orders", return_value=2):
            self.assertEqual(order_tasks.cancel_expired_pending_orders_task(), 2)
        with patch.object(order_tasks, "mark_due_physical_orders_signed", return_value=1):
            self.assertEqual(order_tasks.mark_due_physical_orders_signed_task(), 1)
        with patch.object(order_tasks, "auto_complete_eligible_physical_order", return_value=3), patch.object(
            order_tasks,
            "auto_complete_eligible_virtual_order",
            return_value=4,
        ):
            self.assertEqual(order_tasks.auto_complete_eligible_orders_task(), 7)

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Listing
from orders.models import Order
from orders.services import create_order

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

    def test_multiple_pending_orders_for_same_listing(self):
        listing = self._create_active_listing()
        another_buyer = User.objects.create_user(
            username="买家C", email="buyerc@test.com", password="testpass123"
        )
        order1 = create_order(self.buyer, listing)
        order2 = create_order(another_buyer, listing)

        self.assertEqual(order1.status, Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order2.status, Order.OrderStatus.PENDING_PAYMENT)
        self.assertEqual(
            Order.objects.filter(
                listing=listing, status=Order.OrderStatus.PENDING_PAYMENT
            ).count(),
            2,
        )

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


class PurchaseConfirmViewTest(TestCase):
    """购买确认视图测试。"""

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
            title="可购买商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
            description="测试描述",
        )

    def test_guest_redirected_to_login(self):
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_get_shows_purchase_confirm_page(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "可购买商品")
        self.assertContains(response, "88.00")
        self.assertContains(response, "模拟支付，不会真实扣款")

    def test_post_creates_order_and_redirects(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        response = self.client.post(url)

        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.buyer, self.buyer)
        self.assertEqual(order.seller, self.seller)
        self.assertRedirects(
            response,
            reverse("orders:order_detail", kwargs={"pk": order.pk}),
        )

    def test_post_self_purchase_redirects_with_error(self):
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("catalog:listing_purchase", kwargs={"pk": self.listing.pk})
        response = self.client.post(url)

        self.assertEqual(Order.objects.count(), 0)
        self.assertRedirects(
            response,
            reverse("catalog:listing_detail", kwargs={"pk": self.listing.pk}),
        )

    def test_post_non_active_listing_redirects_with_error(self):
        self.client.login(username="买家A", password="testpass123")
        withdrawn_listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="已下架商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.WITHDRAWN,
            price=Decimal("50.00"),
            description="测试",
        )
        url = reverse("catalog:listing_purchase", kwargs={"pk": withdrawn_listing.pk})
        response = self.client.post(url)

        self.assertEqual(Order.objects.count(), 0)
        self.assertRedirects(
            response,
            reverse("catalog:listing_detail", kwargs={"pk": withdrawn_listing.pk}),
            fetch_redirect_response=False,
        )


class OrderDetailViewTest(TestCase):
    """订单详情视图测试。"""

    @classmethod
    def setUpTestData(cls):
        cls.buyer = User.objects.create_user(
            username="买家A", email="buyer@test.com", password="testpass123"
        )
        cls.seller = User.objects.create_user(
            username="卖家B", email="seller@test.com", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="路人C", email="other@test.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="数码产品")
        cls.listing = Listing.objects.create(
            owner=cls.seller,
            category=cls.category,
            title="测试商品",
            item_type=Listing.ItemType.PHYSICAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("120.00"),
            description="测试描述",
        )
        cls.order = Order.objects.create(
            buyer=cls.buyer,
            seller=cls.seller,
            listing=cls.listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="测试商品",
            order_price=Decimal("120.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )

    def test_buyer_can_access_order_detail(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "测试商品")
        self.assertContains(response, "120.00")

    def test_seller_can_access_order_detail(self):
        self.client.login(username="卖家B", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "测试商品")

    def test_unrelated_user_gets_404(self):
        self.client.login(username="路人C", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_guest_redirected_to_login(self):
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_nonexistent_order_returns_404(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_pending_payment_shows_mock_payment_button(self):
        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": self.order.pk})
        response = self.client.get(url)
        self.assertContains(response, "模拟支付")
        self.assertContains(response, "模拟支付，不会真实扣款")

    def test_order_detail_shows_snapshot_after_listing_deleted(self):
        temp_listing = Listing.objects.create(
            owner=self.seller,
            category=self.category,
            title="即将删除的商品",
            item_type=Listing.ItemType.VIRTUAL,
            status=Listing.Status.ACTIVE,
            price=Decimal("30.00"),
            description="测试",
        )
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=temp_listing,
            buyer_display_name="买家A",
            seller_display_name="卖家B",
            listing_title_snapshot="即将删除的商品",
            order_price=Decimal("30.00"),
            payment_deadline=timezone.now() + timedelta(minutes=15),
        )
        temp_listing.delete()
        order.refresh_from_db()
        self.assertIsNone(order.listing)

        self.client.login(username="买家A", password="testpass123")
        url = reverse("orders:order_detail", kwargs={"pk": order.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "即将删除的商品")

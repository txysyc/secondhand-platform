from datetime import timedelta
import random

from django.utils import timezone
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from users.models import User, UserAddress
from catalog.models import Listing
from orders.models import Order


def create_order(buyer: User, listing: Listing, address_id=None) -> Order:
    """为买家创建待支付订单；同一商品只允许一个未过期待支付订单。"""
    now = timezone.now()

    with transaction.atomic():
        try:
            listing = (
                Listing.objects.select_for_update(of=("self",))
                .select_related("owner")
                .get(pk=listing.pk)
            )
        except Listing.DoesNotExist:
            raise ValidationError("该商品不存在")

        seller: User = listing.owner

        if buyer == seller:
            raise PermissionDenied("用户不能购买自己发布的商品")
        if listing.status != Listing.Status.ACTIVE:
            raise ValidationError("该商品不能购买")

        address = None
        if listing.item_type == Listing.ItemType.PHYSICAL:
            if not address_id:
                raise ValidationError("实体商品订单必须选择收货地址")
            try:
                address = UserAddress.objects.get(pk=address_id, user=buyer)
            except UserAddress.DoesNotExist:
                raise ValidationError("收货地址不存在或无权使用")

        has_active_pending_order = Order.objects.filter(
            listing=listing,
            status=Order.OrderStatus.PENDING_PAYMENT,
            payment_deadline__gte=now,
        ).exists()
        if has_active_pending_order:
            raise ValidationError("该商品已有待支付订单，请稍后再试")

        first_image = listing.images.order_by("sort_order", "id").first()
        listing_image_snapshot = first_image.image.url if first_image else ""

        kwargs = {
            "buyer": buyer,
            "seller": seller,
            "listing": listing,
            "buyer_display_name": buyer.profile.nickname or buyer.username,
            "seller_display_name": seller.profile.nickname or seller.username,
            "listing_title_snapshot": listing.title,
            "listing_image_snapshot": listing_image_snapshot,
            "status": Order.OrderStatus.PENDING_PAYMENT,
            "order_price": listing.price,
            "payment_deadline": now + timedelta(minutes=15),
        }
        if address is not None:
            kwargs.update(
                {
                    "shipping_recipient_name": address.recipient_name,
                    "shipping_phone": address.phone,
                    "shipping_province": address.province,
                    "shipping_city": address.city,
                    "shipping_district": address.district,
                    "shipping_detail_address": address.detail_address,
                }
            )
        order = Order.objects.create(**kwargs)

    return order


def pay_order(buyer, order_id):
    """完成模拟支付，并把订单和商品推进到交易占用状态。"""
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(id=order_id)
        except Order.DoesNotExist:
            raise ValidationError("该订单不存在")

        if order.listing_id is None:
            raise ValidationError("关联商品不存在，无法支付")
        try:
            listing = Listing.objects.select_for_update().get(pk=order.listing_id)
        except Listing.DoesNotExist:
            raise ValidationError("该商品不存在")
        now = timezone.now()

        if buyer != order.buyer:
            raise PermissionDenied("无权购买")

        if order.status != Order.OrderStatus.PENDING_PAYMENT:
            raise ValidationError("该订单已支付或已取消，请勿重复购买")
        if order.payment_deadline < now:
            order.status = Order.OrderStatus.CANCELLED
            order.cancelled_at = now
            order.save(update_fields=["status", "cancelled_at", "updated_at"])
            raise ValidationError("订单已超时，系统已自动取消")
        if listing.status != Listing.Status.ACTIVE:
            raise ValidationError("商品已不可购买，支付失败")

        # 支付成功是订单与商品状态第一次联动，必须在同一事务内提交。
        order.status = Order.OrderStatus.AWAITING_SHIPMENT
        order.paid_at = now
        listing.status = Listing.Status.RESERVED

        order.save(update_fields=["status", "paid_at", "updated_at"])
        listing.save(update_fields=["status"])
        return order


def cancel_expired_pending_orders():
    """取消已超过支付截止时间且仍待支付的订单。"""
    now = timezone.now()
    updated = Order.objects.filter(
        status=Order.OrderStatus.PENDING_PAYMENT, payment_deadline__lt=now
    ).update(
        status=Order.OrderStatus.CANCELLED,
        updated_at=now,
        cancelled_at=now,
    )

    return updated


def confirm_order_delivery(seller, order_id):
    """卖家确认发货或交付，使订单进入买家确认收货阶段。"""
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(id=order_id)
        except Order.DoesNotExist:
            raise ValidationError("订单不存在")

        try:
            listing = Listing.objects.select_for_update().get(id=order.listing_id)
        except Listing.DoesNotExist:
            raise ValidationError("订单关联商品不存在")

        if seller.pk != order.seller_id:
            raise PermissionDenied("无权访问该订单")

        if order.status != Order.OrderStatus.AWAITING_SHIPMENT:
            raise ValidationError("订单不是待发货状态")
        if listing.status != Listing.Status.RESERVED:
            raise ValidationError("订单关联商品不处于交易状态")

        # 交付确认只推进订单状态；商品继续保持 reserved，直到订单完成。
        order.status = Order.OrderStatus.AWAITING_RECEIPT
        order.shipped_at = timezone.now()

        if listing.item_type == Listing.ItemType.PHYSICAL:
            # 实体商品只在卖家确认发货时生成一次模拟签收时间。
            seconds = random.randint(24 * 60 * 60, 5 * 24 * 60 * 60)
            order.logistics_signed_due_at = order.shipped_at + timedelta(
                seconds=seconds
            )
        else:
            order.logistics_signed_due_at = None

        order.save(
            update_fields=[
                "status",
                "shipped_at",
                "logistics_signed_due_at",
                "updated_at",
            ]
        )


def confirm_order_receipt(buyer, order_id):
    """买家确认收货并完成订单。"""
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(id=order_id)
        except Order.DoesNotExist:
            raise ValidationError("该订单不存在")

        try:
            listing = Listing.objects.select_for_update().get(id=order.listing_id)
        except Listing.DoesNotExist:
            raise ValidationError("订单关联商品不存在")

        if buyer.pk != order.buyer_id:
            raise PermissionDenied("无权操作该订单")

        # 实体商品可提前确认收货；虚拟商品只允许在待收货阶段确认完成。
        if listing.item_type == Listing.ItemType.PHYSICAL and not (
            order.status == Order.OrderStatus.SIGNED
            or order.status == Order.OrderStatus.AWAITING_RECEIPT
        ):
            raise ValidationError("实体商品订单不能确认收货")

        if (
            listing.item_type == Listing.ItemType.VIRTUAL
            and order.status != Order.OrderStatus.AWAITING_RECEIPT
        ):
            raise ValidationError("虚拟商品订单不是待收货状态")
        if listing.status != Listing.Status.RESERVED:
            raise ValidationError("关联商品不处于交易状态")

        # 订单完成时才把商品从交易占用推进为已售出。
        order.status = Order.OrderStatus.COMPLETED
        order.completed_at = timezone.now()
        listing.status = Listing.Status.SOLD

        order.save(update_fields=["status", "completed_at", "updated_at"])
        listing.save(update_fields=["status", "updated_at"])


def mark_due_physical_orders_signed(now=None):
    """将到达模拟签收时间的实体商品订单标记为已签收。"""
    now = now or timezone.now()

    orders = Order.objects.filter(
        status=Order.OrderStatus.AWAITING_RECEIPT,
        logistics_signed_due_at__lte=now,
        listing__item_type=Listing.ItemType.PHYSICAL,
    )
    updated = orders.update(
        status=Order.OrderStatus.SIGNED,
        signed_at=now,
        updated_at=now,
    )

    return updated


def auto_complete_eligible_physical_order(now=None):
    """自动完成签收满 3 天且商品仍被交易占用的实体商品订单。"""
    now = now or timezone.now()
    with transaction.atomic():
        # 自动任务可能与买家手动确认并发，先锁定候选订单再批量推进。
        orders = Order.objects.select_for_update(of=("self",)).filter(
            status=Order.OrderStatus.SIGNED,
            signed_at__lte=now - timedelta(days=3),
            listing__item_type=Listing.ItemType.PHYSICAL,
            listing__status=Listing.Status.RESERVED,
        )
        listing_ids = set(orders.values_list("listing_id", flat=True))
        updated = orders.update(
            status=Order.OrderStatus.COMPLETED, completed_at=now, updated_at=now
        )
        Listing.objects.filter(id__in=listing_ids).update(status=Listing.Status.SOLD)
    return updated


def auto_complete_eligible_virtual_order(now=None):
    """自动完成交付满 7 天且商品仍被交易占用的虚拟商品订单。"""
    now = now or timezone.now()
    with transaction.atomic():
        # 虚拟商品没有模拟签收阶段，自动完成窗口从卖家交付时间开始计算。
        orders = Order.objects.select_for_update(of=("self",)).filter(
            status=Order.OrderStatus.AWAITING_RECEIPT,
            shipped_at__lte=now - timedelta(days=7),
            listing__item_type=Listing.ItemType.VIRTUAL,
            listing__status=Listing.Status.RESERVED,
        )
        listing_ids = set(orders.values_list("listing_id", flat=True))
        updated = orders.update(
            status=Order.OrderStatus.COMPLETED, completed_at=now, updated_at=now
        )
        Listing.objects.filter(id__in=listing_ids).update(status=Listing.Status.SOLD)
    return updated

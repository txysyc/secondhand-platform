from datetime import timedelta

from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.db import transaction

from users.models import User
from catalog.models import Listing
from orders.models import Order


def create_order(buyer: User, listing: Listing) -> Order:
    seller: User = listing.owner

    if buyer == seller:
        raise PermissionDenied("用户不能购买自己发布的商品")
    if listing.status != Listing.Status.ACTIVE:
        raise ValidationError("该商品不能购买")

    kwargs = {
        "buyer": buyer,
        "seller": seller,
        "listing": listing,
        "buyer_display_name": buyer.profile.nickname or buyer.username,
        "seller_display_name": seller.profile.nickname or seller.username,
        "listing_title_snapshot": listing.title,
        "status": Order.OrderStatus.PENDING_PAYMENT,
        "order_price": listing.price,
        "payment_deadline": timezone.now() + timedelta(minutes=15),
    }
    with transaction.atomic():
        order = Order.objects.create(**kwargs)

    return order


def pay_order(buyer, order_id):
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

        order.status = Order.OrderStatus.AWAITING_SHIPMENT
        order.paid_at = now
        listing.status = Listing.Status.RESERVED

        order.save(update_fields=["status", "paid_at", "updated_at"])
        listing.save(update_fields=["status"])
        return order


def cancel_expired_pending_orders():
    now = timezone.now()
    updated = Order.objects.filter(
        status=Order.OrderStatus.PENDING_PAYMENT, payment_deadline__lt=now
    ).update(
        status=Order.OrderStatus.CANCELLED,
        updated_at=now,
        cancelled_at=now,
    )

    return updated

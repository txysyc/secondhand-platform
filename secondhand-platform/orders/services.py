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

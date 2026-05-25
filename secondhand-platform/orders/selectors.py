from orders.models import Order


def get_buyer_orders(user):
    if user is None or not user.is_authenticated:
        return Order.objects.none()
    return (
        Order.objects.select_related("buyer", "seller", "listing")
        .filter(buyer=user)
        .order_by("-created_at")
    )


def get_seller_orders(user):
    if user is None or not user.is_authenticated:
        return Order.objects.none()
    return (
        Order.objects.select_related("buyer", "seller", "listing")
        .filter(seller=user)
        .order_by("-created_at")
    )

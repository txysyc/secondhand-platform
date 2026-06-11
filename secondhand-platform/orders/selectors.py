from orders.models import Order


def get_buyer_orders(user):
    """读取当前用户作为买家的订单列表。"""

    if user is None or not user.is_authenticated:
        return Order.objects.none()
    return (
        Order.objects.select_related("buyer", "seller", "listing")
        .filter(buyer=user)
        .order_by("-created_at")
    )


def get_seller_orders(user):
    """读取当前用户作为卖家的订单列表。"""

    if user is None or not user.is_authenticated:
        return Order.objects.none()
    return (
        Order.objects.select_related("buyer", "seller", "listing")
        .filter(seller=user)
        .order_by("-created_at")
    )

from orders.models import Order


def get_order_queryset():
    """返回订单 API 可复用的基础查询集。"""

    return Order.objects.select_related(
        "buyer",
        "seller",
        "listing",
        "listing__category",
        "listing__owner",
        "listing__owner__profile",
    )


def get_buyer_orders(user):
    """读取当前用户作为买家的订单列表。"""

    if user is None or not user.is_authenticated:
        return Order.objects.none()
    return (
        get_order_queryset()
        .filter(buyer=user)
        .order_by("-created_at")
    )


def get_seller_orders(user):
    """读取当前用户作为卖家的订单列表。"""

    if user is None or not user.is_authenticated:
        return Order.objects.none()
    return (
        get_order_queryset()
        .filter(seller=user)
        .order_by("-created_at")
    )


def get_order_viewer_role(order, user):
    """判断当前用户在订单中的身份。"""

    if user is None or not user.is_authenticated:
        return None
    if order.buyer_id == user.id:
        return "buyer"
    if order.seller_id == user.id:
        return "seller"
    return None


def is_order_payment_expired(order, now=None):
    """判断待支付订单是否已经超过支付截止时间。"""

    from django.utils import timezone

    now = now or timezone.now()
    return (
        order.status == Order.OrderStatus.PENDING_PAYMENT
        and order.payment_deadline < now
    )


def get_order_available_actions(order, user, now=None):
    """根据订单状态和访问者身份返回前端可展示动作。"""

    role = get_order_viewer_role(order, user)
    if role == "buyer":
        if (
            order.status == Order.OrderStatus.PENDING_PAYMENT
            and not is_order_payment_expired(order, now=now)
        ):
            return ["pay"]
        if order.status in [
            Order.OrderStatus.AWAITING_RECEIPT,
            Order.OrderStatus.SIGNED,
        ]:
            return ["confirm_receipt"]

    if role == "seller" and order.status == Order.OrderStatus.AWAITING_SHIPMENT:
        return ["confirm_delivery"]

    return []

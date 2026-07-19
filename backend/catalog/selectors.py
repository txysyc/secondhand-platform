from django.db.models import Q
from catalog.cache import _active_category_ids_cache_key, get_active_category_ids
from catalog.models import Category, Listing


def get_active_categories():
    """返回当前启用分类的 QuerySet。

    先复用缓存中的启用分类 ID 列表，再重新构造 QuerySet，保证调用方仍能按
    Django QuerySet 的方式继续过滤、排序或序列化。
    """

    category_ids = get_active_category_ids()
    if not category_ids:
        return Category.objects.none()
    # 通过 ID 重新构造 QuerySet，保留调用方继续链式查询的能力。
    return Category.objects.filter(id__in=category_ids).order_by("id")


def get_public_listing_queryset():
    """构建公开商品列表 API 使用的商品查询。

    默认只返回在售且所属分类仍启用的商品；具体筛选由 FilterSet 负责，
    selector 只维护公开可见性、关联预取和默认排序。
    """

    active_category_ids = get_active_category_ids()
    if not active_category_ids:
        # 没有启用分类时，公开列表一定为空，直接返回空 QuerySet。
        return Listing.objects.none()

    # 公开列表只展示在售商品，并排除所属分类已停用的商品。
    listing_queryset = (
        Listing.objects.filter(
            status=Listing.Status.ACTIVE,
            category_id__in=active_category_ids,
        )
        .select_related("category", "owner", "owner__profile")
        .prefetch_related("images")
        .order_by("-published_at", "-id")
    )
    return listing_queryset


def get_public_listing_detail_queryset():
    """构建公开商品详情 API 使用的可见商品查询。"""

    return (
        Listing.objects.select_related("category", "owner", "owner__profile")
        .prefetch_related("images")
        .filter(status=Listing.Status.ACTIVE, category__is_active=True)
    )


def get_visible_listing_detail_queryset(user):
    """构建商品详情 API 对当前访问者可见的商品查询。

    公开访客只能访问在售商品；登录后，卖家可查看自己发布的商品，已支付交易的
    买家可继续查看交易中的或已售出的商品详情。
    """

    queryset = Listing.objects.select_related(
        "category",
        "owner",
        "owner__profile",
    ).prefetch_related("images")
    public_filter = Q(status=Listing.Status.ACTIVE, category__is_active=True)

    if user is None or not user.is_authenticated:
        return queryset.filter(public_filter)

    from orders.models import Order

    paid_order_statuses = [
        Order.OrderStatus.AWAITING_SHIPMENT,
        Order.OrderStatus.AWAITING_RECEIPT,
        Order.OrderStatus.SIGNED,
        Order.OrderStatus.COMPLETED,
    ]
    participant_filter = Q(owner=user) | Q(
        status__in=[Listing.Status.RESERVED, Listing.Status.SOLD],
        orders__buyer=user,
        orders__status__in=paid_order_statuses,
    )
    return queryset.filter(public_filter | participant_filter).distinct()


def get_owner_listing_queryset(user):
    """构建当前用户自己的商品列表 API 查询。"""

    if user is None or not user.is_authenticated:
        return Listing.objects.none()
    return (
        Listing.objects.filter(owner=user)
        # 已售出商品已进入订单履约闭环，不再出现在我的商品管理列表。
        .exclude(status=Listing.Status.SOLD)
        .select_related("category", "owner", "owner__profile")
        .prefetch_related("images")
        .order_by("-updated_at", "-id")
    )

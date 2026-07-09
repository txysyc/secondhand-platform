from time import time_ns

from django.core.cache import cache
from django.db.models import Q
from catalog.models import Category, Listing

CACHE_KEY_ACTIVE_CATEGORY_IDS = "catalog:active_category_ids"
CACHE_KEY_ACTIVE_CATEGORY_VERSION = "catalog:active_category_ids:version"
CACHE_TIMEOUT_ACTIVE_CATEGORY_IDS = 60 * 10

def clear_active_category_cache():
    """递增启用分类缓存版本号，供分类保存或删除信号调用。"""

    try:
        cache.incr(CACHE_KEY_ACTIVE_CATEGORY_VERSION)
    except ValueError:
        cache.set(
            CACHE_KEY_ACTIVE_CATEGORY_VERSION,
            _new_category_cache_version(),
            None,
        )


def get_active_category_ids():
    """读取启用分类 ID 列表。

    只缓存稳定的小型 ID 列表，调用方仍返回 QuerySet 或继续做数据库过滤，
    避免缓存完整模型对象导致 API 查询行为变得隐晦。
    """

    cache_key = _active_category_ids_cache_key()
    category_ids = cache.get(cache_key)
    if category_ids is None or _active_category_cache_is_stale(category_ids):
        category_ids = _refresh_active_category_ids_cache(cache_key)
    return category_ids


def _refresh_active_category_ids_cache(cache_key):
    """从数据库刷新启用分类 ID 缓存。"""

    # 缓存未命中或缓存陈旧时只查询启用分类的主键，避免把模型实例直接写入缓存。
    category_ids = list(
        Category.objects.filter(is_active=True)
        .order_by("id")
        .values_list("id", flat=True)
    )
    cache.set(
        cache_key,
        category_ids,
        CACHE_TIMEOUT_ACTIVE_CATEGORY_IDS,
    )
    return category_ids


def _active_category_cache_is_stale(category_ids):
    """判断启用分类缓存是否已与数据库不一致。"""

    cached_ids = set(category_ids or [])
    # 兼容手工导入、测试清表或缓存服务残留导致的信号未触发场景。
    current_ids = set(
        Category.objects.filter(is_active=True).values_list("id", flat=True)
    )
    return cached_ids != current_ids


def _active_category_ids_cache_key():
    """生成当前启用分类 ID 列表使用的版本化缓存 key。"""

    version = cache.get(CACHE_KEY_ACTIVE_CATEGORY_VERSION)
    if version is None:
        version = _new_category_cache_version()
        cache.add(CACHE_KEY_ACTIVE_CATEGORY_VERSION, version, None)
        version = cache.get(CACHE_KEY_ACTIVE_CATEGORY_VERSION) or version
    return f"{CACHE_KEY_ACTIVE_CATEGORY_IDS}:v{version}"


def _new_category_cache_version():
    """生成不易与旧缓存 key 碰撞的分类缓存版本号。"""

    return time_ns()


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


def apply_public_listing_sort(queryset, sort: str | None):
    """按公开列表允许的排序白名单处理排序参数。"""

    # 排序字段保持白名单匹配，避免把请求参数直接拼进 order_by。
    match sort:
        case "oldest":
            return queryset.order_by("published_at", "id")
        case "price_asc":
            return queryset.order_by("price", "id")
        case "price_desc":
            return queryset.order_by("-price", "-id")
        case _:
            return queryset.order_by("-published_at", "-id")


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


def apply_owner_listing_sort(queryset, sort: str | None):
    """按我的商品管理允许的排序白名单处理排序参数。"""

    # 排序字段保持白名单匹配，避免把请求参数直接拼进 order_by。
    match sort:
        case "updated_asc":
            return queryset.order_by("updated_at", "id")
        case "published_desc":
            return queryset.order_by("-published_at", "-id")
        case "published_asc":
            return queryset.order_by("published_at", "id")
        case "price_asc":
            return queryset.order_by("price", "id")
        case "price_desc":
            return queryset.order_by("-price", "-id")
        case _:
            return queryset.order_by("-updated_at", "-id")

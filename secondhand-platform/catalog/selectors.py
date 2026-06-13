from typing import Any
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
    if category_ids is None:
        # 缓存未命中时只查询启用分类的主键，避免把模型实例直接写入缓存。
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


def get_public_listing_queryset(filters: dict[str, Any] | None = None):
    """构建公开商品列表 API 使用的商品查询。

    默认只返回在售且所属分类仍启用的商品；传入已校验的筛选参数时，
    继续叠加关键词、分类、类型、价格区间和排序条件。
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
    if not filters:
        return listing_queryset

    # 以下筛选条件来自 serializer 校验后的数据；空值保持默认公开列表。
    q = filters.get("q")
    if q:
        listing_queryset = listing_queryset.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
        )

    category = filters.get("category")
    if category is not None:
        listing_queryset = listing_queryset.filter(category=category)

    item_type = filters.get("item_type")
    if item_type:
        listing_queryset = listing_queryset.filter(item_type=item_type)

    max_price = filters.get("max_price")
    min_price = filters.get("min_price")
    if max_price is not None and min_price is not None:
        listing_queryset = listing_queryset.filter(
            price__lte=max_price, price__gte=min_price
        )

    sort = filters.get("sort")
    if sort:
        # 排序字段保持白名单匹配，避免把请求参数直接拼进 order_by。
        match sort:
            case "newest":
                listing_queryset = listing_queryset.order_by("-published_at")
            case "oldest":
                listing_queryset = listing_queryset.order_by("published_at")
            case "price_asc":
                listing_queryset = listing_queryset.order_by("price", "id")
            case "price_desc":
                listing_queryset = listing_queryset.order_by("-price", "-id")

    return listing_queryset


def get_public_listing_detail_queryset():
    """构建公开商品详情 API 使用的可见商品查询。"""

    return (
        Listing.objects.select_related("category", "owner", "owner__profile")
        .prefetch_related("images")
        .filter(status=Listing.Status.ACTIVE, category__is_active=True)
    )


def get_owner_listing_queryset(user):
    """构建当前用户自己的商品列表 API 查询。"""

    if user is None or not user.is_authenticated:
        return Listing.objects.none()
    return (
        Listing.objects.filter(owner=user)
        .select_related("category", "owner", "owner__profile")
        .prefetch_related("images")
        .order_by("-updated_at", "-id")
    )

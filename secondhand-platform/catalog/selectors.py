from typing import Any
from collections import OrderedDict
from time import time_ns

from django.core.cache import cache
from django.db.models import Q
from catalog.models import Category, Listing

CACHE_KEY_ACTIVE_CATEGORY_IDS = "catalog:active_category_ids"
CACHE_KEY_ACTIVE_CATEGORY_VERSION = "catalog:active_category_ids:version"
CACHE_TIMEOUT_ACTIVE_CATEGORY_IDS = 60 * 10

# 卖家“我的商品”页面的稳定分组顺序与中文展示文案。
# 顺序与状态值都不应被调用方覆盖；模板和 selector 都直接依赖这一份契约。
_OWNER_LISTING_GROUP_DEFINITIONS = (
    {
        "status": Listing.Status.DRAFT,
        "title": "草稿",
        "description": "尚未发布的商品，可继续编辑后发布或保留为草稿。",
        "empty_text": "还没有保存任何草稿。",
    },
    {
        "status": Listing.Status.ACTIVE,
        "title": "在售",
        "description": "已经发布、可被买家看到的商品。",
        "empty_text": "目前没有在售商品。",
    },
    {
        "status": Listing.Status.RESERVED,
        "title": "交易占用",
        "description": "买家已下单并占用，由订单流程控制，不可手动改变。",
        "empty_text": "目前没有商品处于交易占用状态。",
    },
    {
        "status": Listing.Status.SOLD,
        "title": "已售出",
        "description": "订单已完成的商品，不能重新上架。",
        "empty_text": "还没有已售出的商品。",
    },
    {
        "status": Listing.Status.WITHDRAWN,
        "title": "已下架",
        "description": "已暂时下架，可在分类仍启用时重新上架。",
        "empty_text": "目前没有已下架的商品。",
    },
)


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
    避免缓存完整模型对象导致表单和模板行为变得隐晦。
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
    Django QuerySet 的方式继续过滤、排序或作为表单字段数据源使用。
    """

    category_ids = get_active_category_ids()
    if not category_ids:
        return Category.objects.none()
    # 通过 ID 重新构造 QuerySet，保留调用方继续链式查询的能力。
    return Category.objects.filter(id__in=category_ids).order_by("id")


def get_owner_listing_groups(user):
    """读取当前卖家的所有商品并按生命周期分组。

    返回顺序固定为草稿、在售、交易占用、已售出、已下架；即使分组为空也会出现，
    保证模板布局稳定，避免卖家误以为状态缺失。
    """

    listings = (
        Listing.objects.filter(owner=user)
        .select_related("category")
        .prefetch_related("images")
        .order_by("-updated_at", "-id")
    )

    # 先按固定生命周期定义创建所有分组，保证空分组也能在页面上稳定展示。
    groups = OrderedDict(
        (
            definition["status"],
            {
                "status": definition["status"],
                "status_display": Listing.Status(definition["status"]).label,
                "title": definition["title"],
                "description": definition["description"],
                "empty_text": definition["empty_text"],
                "listings": [],  # 所含商品
                "count": 0,
            },
        )
        for definition in _OWNER_LISTING_GROUP_DEFINITIONS
    )

    for listing in listings:
        # 按商品状态把每个商品放入对应分组，供模板直接按组渲染。
        bucket = groups.get(listing.status)
        if bucket is None:
            # 防御未来新增状态：未知状态不会污染既有分组，等模型扩展再补 selector。
            continue
        bucket["listings"].append(listing)
        bucket["count"] += 1

    return list(groups.values())


def get_publish_listing_queryset(cleaned_data: dict[str, Any] | None = None):
    """构建公开商品列表页使用的商品查询。

    默认只返回在售且所属分类仍启用的商品；传入筛选表单清洗后的数据时，
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
    if not cleaned_data:
        return listing_queryset

    # 以下筛选条件来自表单 clean 后的数据；空值保持默认公开列表。
    q = cleaned_data.get("q")
    if q:
        listing_queryset = listing_queryset.filter(
            Q(title__icontains=q) | Q(description__icontains=q)
        )

    category = cleaned_data.get("category")
    if category is not None:
        listing_queryset = listing_queryset.filter(category=category)

    item_type = cleaned_data.get("item_type")
    if item_type:
        listing_queryset = listing_queryset.filter(item_type=item_type)

    max_price = cleaned_data.get("max_price")
    min_price = cleaned_data.get("min_price")
    if max_price is not None and min_price is not None:
        listing_queryset = listing_queryset.filter(
            price__lte=max_price, price__gte=min_price
        )

    sort = cleaned_data.get("sort")
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

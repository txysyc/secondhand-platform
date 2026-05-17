from collections import OrderedDict

from catalog.models import Category, Listing


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


def get_active_categories():
    return Category.objects.filter(is_active=True).order_by("id")


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

    # 构建一个顺序字典
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
        bucket = groups.get(listing.status)
        if bucket is None:
            # 防御未来新增状态：未知状态不会污染既有分组，等模型扩展再补 selector。
            continue
        bucket["listings"].append(listing)
        bucket["count"] += 1

    return list(groups.values())

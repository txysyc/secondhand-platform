from django.db.models import Prefetch
from django.db.models import BooleanField, Exists, OuterRef, Value

from catalog.models import Listing
from catalog.selectors import get_visible_listing_detail_queryset
from interactions.models import Comment, ListingFavorite, ListingViewHistory


def get_listing_comments(listing: Listing):
    """读取商品的所属评论以及二级评论"""
    # 预取作者及主页，以便可以点击其公开主页
    comments = (
        Comment.objects.select_related("listing", "author", "author__profile")
        .prefetch_related(
            Prefetch(
                "replies",
                queryset=Comment.objects.select_related(
                    "listing", "author", "author__profile"
                )
                .filter(listing=listing)
                .order_by("created_at", "id"),
            )
        )
        .filter(listing=listing, parent__isnull=True)
        .order_by("created_at", "id")
    )

    return comments


def annotate_listings_with_favorite_status(queryset, user):
    """为商品查询集补充当前用户是否已收藏的布尔标记。"""

    if user is None or not user.is_authenticated:
        return queryset.annotate(
            is_favorited=Value(False, output_field=BooleanField()),
        )

    favorite_queryset = ListingFavorite.objects.filter(
        user=user,
        listing_id=OuterRef("pk"),
    )
    return queryset.annotate(is_favorited=Exists(favorite_queryset))


def get_user_favorite_items(user):
    """读取当前用户可见的收藏记录，并预取商品展示需要的关联数据。"""

    if user is None or not user.is_authenticated:
        return ListingFavorite.objects.none()

    visible_listing_ids = get_visible_listing_detail_queryset(user).values("id")
    listing_queryset = annotate_listings_with_favorite_status(
        Listing.objects.select_related("category", "owner", "owner__profile")
        .prefetch_related("images")
        .filter(id__in=visible_listing_ids),
        user,
    )
    return (
        ListingFavorite.objects.filter(user=user, listing_id__in=visible_listing_ids)
        .select_related("user")
        .prefetch_related(Prefetch("listing", queryset=listing_queryset))
        .order_by("-created_at", "-id")
    )


def get_user_view_history_items(user):
    """读取当前用户可见的浏览历史，并预取商品展示需要的关联数据。"""

    if user is None or not user.is_authenticated:
        return ListingViewHistory.objects.none()

    visible_listing_ids = get_visible_listing_detail_queryset(user).values("id")
    listing_queryset = annotate_listings_with_favorite_status(
        Listing.objects.select_related("category", "owner", "owner__profile")
        .prefetch_related("images")
        .filter(id__in=visible_listing_ids),
        user,
    )
    return (
        ListingViewHistory.objects.filter(user=user, listing_id__in=visible_listing_ids)
        .select_related("user")
        .prefetch_related(Prefetch("listing", queryset=listing_queryset))
        .order_by("-viewed_at", "-id")
    )

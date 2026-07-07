from django.db.models import Prefetch

from catalog.models import Listing
from interactions.models import Comment


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

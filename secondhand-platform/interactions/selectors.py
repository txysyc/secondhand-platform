from catalog.models import Listing
from interactions.models import Comment


def get_listing_comments(listing):
    """读取商品的所属评论"""
    comments = Comment.objects.select_related(
        "listing", "author", "author__profile"
    ).filter(listing=listing)

    return comments

from rest_framework.exceptions import PermissionDenied, ValidationError
from users.models import User
from catalog.models import Listing
from interactions.models import Comment, ListingFavorite, ListingViewHistory
from notifications.models import Notification
from notifications.services import create_notification_after_commit

MAX_VIEW_HISTORY_PER_USER = 100


def create_comment(user: User, listing: Listing, content: str):
    """创建顶层留言"""
    comment = _create_comment(user=user, listing=listing, content=content, parent=None)
    create_notification_after_commit(
        recipient=listing.owner,
        actor=user,
        type=Notification.NotificationType.LISTING_COMMENTED,
        title="商品收到新评论",
        content=f"{user.username} 评论了你的商品《{listing.title}》",
        target_type=Notification.TargetType.LISTING,
        target_id=listing.pk,
        target_url=f"/listings/{listing.pk}",
        payload={"listing_id": listing.pk, "comment_id": comment.pk},
    )
    return comment


def create_reply(user: User, parent_comment: Comment, content: str):
    """回复留言"""
    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权创建评论")
    if parent_comment.parent_id is not None:
        raise ValidationError("不得创建多级留言")

    reply = _create_comment(
        user=user,
        listing=parent_comment.listing,
        content=content,
        parent=parent_comment,
    )
    create_notification_after_commit(
        recipient=parent_comment.author,
        actor=user,
        type=Notification.NotificationType.COMMENT_REPLIED,
        title="评论收到回复",
        content=f"{user.username} 回复了你在《{parent_comment.listing.title}》下的评论",
        target_type=Notification.TargetType.LISTING,
        target_id=parent_comment.listing_id,
        target_url=f"/listings/{parent_comment.listing_id}",
        payload={
            "listing_id": parent_comment.listing_id,
            "comment_id": parent_comment.pk,
            "reply_id": reply.pk,
        },
    )
    return reply


def delete_comment(user: User, comment: Comment):
    """删除留言"""
    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权删除评论")
    if comment.author != user:
        raise PermissionDenied("当前用户无权删除该评论")

    comment.delete()


def favorite_listing(user: User, listing: Listing):
    """收藏当前用户可见的商品，重复收藏时直接返回已有记录。"""

    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权收藏商品")
    # 收藏只面向买家行为，卖家不能收藏自己发布的商品。
    if listing.owner_id == user.id:
        raise PermissionDenied("不能收藏自己发布的商品")

    favorite, _ = ListingFavorite.objects.get_or_create(
        user=user,
        listing=listing,
    )
    return favorite


def unfavorite_listing(user: User, listing_id: int):
    """取消当前用户的商品收藏，未收藏时保持幂等成功。"""

    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权取消收藏")

    ListingFavorite.objects.filter(user=user, listing_id=listing_id).delete()


def record_listing_view(user: User, listing: Listing):
    """记录当前用户浏览商品的时间，并裁剪过旧浏览历史。"""

    if user is None or not user.is_authenticated:
        return None

    view_history, _ = ListingViewHistory.objects.update_or_create(
        user=user,
        listing=listing,
        defaults={},
    )
    _trim_user_view_history(user)
    return view_history


def _trim_user_view_history(user: User):
    """只保留当前用户最近固定数量的浏览历史。"""

    keep_ids = list(
        ListingViewHistory.objects.filter(user=user)
        .order_by("-viewed_at", "-id")
        .values_list("id", flat=True)[:MAX_VIEW_HISTORY_PER_USER]
    )
    ListingViewHistory.objects.filter(user=user).exclude(id__in=keep_ids).delete()


def can_interact_with_listing(listing: Listing):
    """判断商品能否互动"""
    return (
        listing.status == Listing.Status.ACTIVE
        and listing.category.is_active is True
    )


def _create_comment(
    user: User, listing: Listing, content: str, parent: Comment | None = None
):
    """创建留言"""
    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权创建评论")

    content = _clean_comment_content(content)

    # 判断商品是否处于可互动状态
    if not can_interact_with_listing(listing):
        raise ValidationError("该商品目前不能发表评论")

    return Comment.objects.create(
        author=user, listing=listing, content=content, parent=parent
    )


def _clean_comment_content(content: str):
    """清洗留言内容"""
    content = (content or "").strip()
    if content == "":
        raise ValidationError("留言内容不能为空")
    if len(content) > 1000:
        raise ValidationError("留言内容不能超过 1000 个字符")

    return content

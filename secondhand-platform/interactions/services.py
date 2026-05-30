from django.core.exceptions import PermissionDenied, ValidationError
from users.models import User
from catalog.models import Listing
from interactions.models import Comment


def create_comment(user: User, listing: Listing, content: str):
    """创建顶层留言"""
    return _create_comment(user=user, listing=listing, content=content, parent=None)


def create_reply(user: User, parent_comment: Comment, content: str):
    """回复留言"""
    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权创建评论")
    if parent_comment.parent_id is not None:
        raise ValidationError("不得创建多级留言")

    return _create_comment(
        user=user,
        listing=parent_comment.listing,
        content=content,
        parent=parent_comment,
    )


def delete_comment(user: User, comment: Comment):
    """删除留言"""
    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权删除评论")
    if comment.author != user:
        raise PermissionDenied("当前用户无权删除该评论")

    comment.delete()


def can_interact_with_listing(listing: Listing):
    """判断商品能否互动"""
    if listing.status == Listing.Status.ACTIVE and listing.category.is_active is True:
        return True
    return False


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

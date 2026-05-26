from django.core.exceptions import PermissionDenied, ValidationError
from users.models import User
from catalog.models import Listing
from interactions.models import Comment


def create_comment(user: User, listing: Listing, content: str):
    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权创建评论")

    content = (content or "").strip()
    if content == "":
        raise ValidationError("留言内容不能为空")
    if len(content) > 1000:
        raise ValidationError("留言内容不能超过 1000 个字符")

    if not listing.category.is_active:
        raise ValidationError("该商品目前不能发表评论")

    # 判断商品是否处于可互动状态（目前以ACTIVE为准）
    if listing.status != Listing.Status.ACTIVE:
        raise ValidationError("该商品目前不能发表评论")

    return Comment.objects.create(author=user, listing=listing, content=content)


def delete_comment(user: User, comment: Comment):
    if user is None or not user.is_authenticated:
        raise PermissionDenied("无权删除评论")
    if comment.author != user:
        raise PermissionDenied("当前用户无权删除该评论")

    comment.delete()

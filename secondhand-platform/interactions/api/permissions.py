"""interactions API 权限。"""

from rest_framework.permissions import BasePermission


class IsCommentAuthor(BasePermission):
    """只允许评论作者删除自己的评论。"""

    message = "当前用户无权删除该评论"

    def has_object_permission(self, request, view, obj):
        return bool(request.user and obj.author_id == request.user.id)

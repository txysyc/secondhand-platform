"""catalog API 权限。"""

from rest_framework.permissions import BasePermission


class IsListingOwner(BasePermission):
    """只允许商品所有者操作商品对象。"""

    message = "该用户无权访问该对象"

    def has_object_permission(self, request, view, obj):
        return bool(request.user and obj.owner_id == request.user.id)

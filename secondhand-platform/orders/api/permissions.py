"""orders API 权限。"""

from rest_framework.permissions import BasePermission


class IsOrderParticipant(BasePermission):
    """只允许订单买家或卖家访问订单。"""

    message = "当前用户无权访问该订单"

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.id in [obj.buyer_id, obj.seller_id]
        )

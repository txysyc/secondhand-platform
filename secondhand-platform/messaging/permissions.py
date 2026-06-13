"""messaging API 权限。"""

from rest_framework.permissions import BasePermission


class IsConversationParticipant(BasePermission):
    """只允许会话参与者访问会话。"""

    message = "无权访问该私信会话"

    def has_object_permission(self, request, view, obj):
        return obj.has_participant(request.user)

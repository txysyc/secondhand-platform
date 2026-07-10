"""站内通知 API 类视图。"""

from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import PageNumberPaginationMixin
from notifications.models import Notification
from notifications.selectors import (
    get_unread_notification_count,
    get_user_notifications,
)
from notifications.serializers import NotificationSerializer
from notifications.services import mark_all_notifications_read, mark_notification_read


class NotificationListApiView(PageNumberPaginationMixin, APIView):
    """当前用户站内通知列表。"""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    max_page_size = 50

    def get(self, request):
        queryset = get_user_notifications(
            request.user,
            request.query_params.get("status", "all"),
        )
        return self.paginate(request, queryset)


class NotificationUnreadCountApiView(APIView):
    """当前用户未读通知数量。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"unread_count": get_unread_notification_count(request.user)})


class NotificationReadApiView(APIView):
    """当前用户单条通知标记已读。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(
            Notification.objects.select_related("actor", "actor__profile"),
            pk=pk,
            recipient=request.user,
        )
        notification = mark_notification_read(request.user, notification)
        return Response(NotificationSerializer(notification).data)


class NotificationReadAllApiView(APIView):
    """当前用户全部通知标记已读。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated_count = mark_all_notifications_read(request.user)
        return Response({"updated_count": updated_count})

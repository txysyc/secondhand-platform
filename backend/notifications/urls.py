"""站内通知 API 路由。"""

from django.urls import path

from notifications.views import (
    NotificationListAPIView,
    NotificationReadAllAPIView,
    NotificationReadAPIView,
    NotificationUnreadCountAPIView,
)

urlpatterns = [
    path("notifications/", NotificationListAPIView.as_view(), name="notifications"),
    path(
        "notifications/unread-count/",
        NotificationUnreadCountAPIView.as_view(),
        name="notifications_unread_count",
    ),
    path(
        "notifications/<int:pk>/read/",
        NotificationReadAPIView.as_view(),
        name="notifications_read",
    ),
    path(
        "notifications/read-all/",
        NotificationReadAllAPIView.as_view(),
        name="notifications_read_all",
    ),
]

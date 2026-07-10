"""站内通知 API 路由。"""

from django.urls import path

from notifications.views import (
    NotificationListApiView,
    NotificationReadAllApiView,
    NotificationReadApiView,
    NotificationUnreadCountApiView,
)

urlpatterns = [
    path("notifications/", NotificationListApiView.as_view(), name="notifications"),
    path(
        "notifications/unread-count/",
        NotificationUnreadCountApiView.as_view(),
        name="notifications_unread_count",
    ),
    path(
        "notifications/<int:pk>/read/",
        NotificationReadApiView.as_view(),
        name="notifications_read",
    ),
    path(
        "notifications/read-all/",
        NotificationReadAllApiView.as_view(),
        name="notifications_read_all",
    ),
]

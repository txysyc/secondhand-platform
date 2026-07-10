from django.contrib import admin

from notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """站内通知后台管理。"""

    list_display = [
        "recipient",
        "actor",
        "type",
        "title",
        "target_type",
        "target_id",
        "read_at",
        "created_at",
    ]
    list_filter = ["type", "target_type", "read_at", "created_at"]
    list_select_related = ["recipient", "actor"]
    readonly_fields = ["created_at"]
    search_fields = ["id", "title", "content", "recipient__username", "actor__username"]
    list_per_page = 20

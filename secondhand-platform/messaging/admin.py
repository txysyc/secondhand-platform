from django.contrib import admin

from messaging.models import Conversation, PrivateMessage


class PrivateMessageInline(admin.TabularInline):
    model = PrivateMessage
    extra = 0
    fields = ["sender", "short_content", "read_at", "created_at"]
    readonly_fields = ["sender", "short_content", "read_at", "created_at"]
    can_delete = False
    max_num = 0

    @admin.display(description="内容摘要")
    def short_content(self, obj):
        return obj.content[:20]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "participant_a",
        "participant_b",
        "message_count",
        "created_at",
        "updated_at",
    ]
    readonly_fields = ["participant_a", "participant_b", "created_at", "updated_at"]
    search_fields = [
        "participant_a__username",
        "participant_b__username",
        "private_messages__content",
    ]
    list_filter = ["created_at", "updated_at"]
    list_select_related = ["participant_a", "participant_b"]
    inlines = [PrivateMessageInline]

    @admin.display(description="消息数")
    def message_count(self, obj):
        return obj.private_messages.count()


@admin.register(PrivateMessage)
class PrivateMessageAdmin(admin.ModelAdmin):
    list_display = [
        "sender",
        "conversation",
        "short_content",
        "read_at",
        "created_at",
    ]
    readonly_fields = ["conversation", "sender", "content", "read_at", "created_at"]
    search_fields = [
        "content",
        "sender__username",
        "conversation__participant_a__username",
        "conversation__participant_b__username",
    ]
    list_filter = ["sender", "read_at", "created_at"]
    list_select_related = ["conversation", "sender"]

    @admin.display(description="内容摘要")
    def short_content(self, obj):
        return obj.content[:20]

from django.contrib import admin

from interactions.models import Comment


class ReplyStatusFilter(admin.SimpleListFilter):
    """按顶层留言或回复筛选后台评论列表。"""

    title = "是否为回复"
    parameter_name = "is_reply"

    def lookups(self, request, model_admin):
        """返回后台筛选器展示的可选项。"""

        return [
            ("yes", "回复"),
            ("no", "顶层留言"),
        ]

    def queryset(self, request, queryset):
        """根据筛选值返回顶层留言或回复查询集。"""

        if self.value() == "yes":
            return queryset.filter(parent__isnull=False)
        if self.value() == "no":
            return queryset.filter(parent__isnull=True)
        return queryset


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """留言后台管理配置。"""

    list_display = [
        "author",
        "listing",
        "parent",
        "is_reply",
        "short_content",
        "created_at",
        "updated_at",
    ]
    readonly_fields = [
        "author",
        "listing",
        "parent",
        "created_at",
        "updated_at",
    ]
    search_fields = ["author__username", "listing__title", "content"]
    list_filter = ["author", ReplyStatusFilter, "created_at", "listing"]
    list_select_related = ["author", "listing", "parent"]

    @admin.display(description="短内容显示")
    def short_content(self, obj):
        """返回后台列表中展示的留言内容摘要。"""

        return obj.content[0:20]

    @admin.display(description="是否为回复")
    def is_reply(self, obj):
        """判断当前留言是否为回复。"""

        return obj.parent is not None

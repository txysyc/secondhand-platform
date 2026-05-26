from django.contrib import admin

from interactions.models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["author", "listing", "short_content", "created_at", "updated_at"]
    readonly_fields = ["author", "listing", "created_at", "updated_at"]
    search_fields = ["author__username", "listing__title", "content"]
    list_filter = ["created_at", "listing"]

    @admin.display(description="短内容显示")
    def short_content(self, obj):
        n = 20
        return obj.content[0:n]

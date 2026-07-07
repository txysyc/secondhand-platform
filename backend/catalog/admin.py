from django.contrib import admin
from django.db.models import Count

from catalog.models import Category, Listing, ListingImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at", "updated_at"]
    list_filter = ["is_active"]
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["id", "name"]
    list_per_page = 20


class ListingInline(admin.TabularInline):
    """在商品后台页直接查看和维护该商品的图片。"""

    model = ListingImage
    verbose_name = "商品图片"
    can_delete = True
    max_num = 6


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = [
        "owner",
        "category",
        "item_type",
        "title",
        "status",
        "price",
        "image_count_value",
        "published_at",
        "created_at",
        "updated_at",
        "condition",
        "delivery_notes_summary",
        "physical_delivery_method",
        "virtual_valid_until",
    ]
    list_filter = [
        "status",
        "category",
        "owner",
        "item_type",
        "created_at",
    ]
    list_select_related = ["owner", "category"]
    readonly_fields = ["created_at", "updated_at", "published_at"]
    search_fields = ["id", "title", "description", "owner__username", "category__name"]
    list_per_page = 20
    inlines = [ListingInline]

    def get_queryset(self, request):
        """返回带图片数量聚合字段的后台商品查询集。"""

        # 列表页一次性聚合图片数量，避免每行单独查询 images。
        queryset = super().get_queryset(request)
        return queryset.annotate(image_count_value=Count("images"))

    @admin.display(description="图片数量", ordering="image_count_value")
    def image_count_value(self, obj):
        """读取后台列表中展示和排序使用的图片数量。"""

        return obj.image_count_value

    @admin.display(description="交付说明摘要")
    def delivery_notes_summary(self, obj):
        """返回后台列表中展示的交付说明前二十个字符。"""

        return obj.delivery_notes[0:20]

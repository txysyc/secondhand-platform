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
        "delivery_notes",
        "physical_delivery_method",
        "virtual_valid_until",
    ]
    list_filter = [
        "category",
        "item_type",
        "status",
        "created_at",
    ]
    list_select_related = ["owner", "category"]
    readonly_fields = ["created_at", "updated_at", "published_at"]
    search_fields = ["id", "title", "description", "owner__username", "category__name"]
    list_per_page = 20
    inlines = [ListingInline]

    def get_queryset(self, request):
        # 列表页一次性聚合图片数量，避免每行单独查询 images。
        queryset = super().get_queryset(request)
        return queryset.annotate(image_count_value=Count("images"))

    @admin.display(description="图片数量", ordering="image_count_value")
    def image_count_value(self, obj):
        return obj.image_count_value

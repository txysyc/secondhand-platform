from django.contrib import admin

from catalog.models import Category, Listing


# Register your models here.
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at", "updated_at"]
    list_filter = ["is_active"]
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["id", "name"]
    list_per_page = 20


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = [
        "owner",
        "category",
        "item_type",
        "title",
        "status",
        "price",
        "created_at",
        "updated_at",
    ]
    list_filter = [
        "category",
        "item_type",
        "status",
        "created_at",
    ]
    list_select_related = ["owner", "category"]
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["id", "title", "description", "owner__username", "category__name"]
    list_per_page = 20

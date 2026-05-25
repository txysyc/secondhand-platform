from django.contrib import admin

from orders.models import Order

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "buyer",
        "seller",
        "listing",
        "status",
        "order_price",
        "payment_deadline",
        "paid_at",
        "shipped_at",
        "signed_at",
        "completed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    ]
    readonly_fields = list_display
    list_filter = [
        "status",
        "created_at",
        "updated_at",
    ]
    search_fields = [
        "buyer__username",
        "seller__username",
        "listing_title_snapshot",
        "buyer_display_name",
        "seller_display_name",
    ]

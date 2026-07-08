from django.contrib import admin

from orders.models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "buyer",
        "seller",
        "listing",
        "status",
        "order_price",
        "shipping_recipient_name",
        "shipping_phone",
        "payment_deadline",
        "paid_at",
        "shipped_at",
        "signed_at",
        "completed_at",
        "cancelled_at",
        "created_at",
        "updated_at",
    ]
    readonly_fields = [*list_display, "logistics_signed_due_at"]
    list_filter = [
        "status",
        "seller",
        "buyer",
        "created_at",
        "updated_at",
    ]
    search_fields = [
        "listing_title_snapshot",
        "buyer_display_name",
        "seller_display_name",
        "buyer__username",
        "seller__username",
        "shipping_recipient_name",
        "shipping_phone",
    ]
    list_select_related = ["buyer", "seller", "listing"]

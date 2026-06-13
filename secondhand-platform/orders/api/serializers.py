"""订单 API 序列化器。"""

from rest_framework import serializers

from catalog.api.serializers import CategorySerializer, ListingOwnerSerializer
from catalog.models import Listing
from orders.models import Order
from orders.selectors import (
    get_order_available_actions,
    get_order_viewer_role,
    is_order_payment_expired,
)


class OrderListingSerializer(serializers.ModelSerializer):
    """订单中的商品摘要，保留快照外的当前商品信息。"""

    category = CategorySerializer(read_only=True)
    owner = ListingOwnerSerializer(read_only=True)
    item_type_display = serializers.CharField(source="get_item_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Listing
        fields = [
            "id",
            "title",
            "category",
            "owner",
            "item_type",
            "item_type_display",
            "status",
            "status_display",
        ]


class OrderUserSerializer(serializers.Serializer):
    """订单买卖双方用户摘要。"""

    id = serializers.IntegerField()
    username = serializers.CharField()


class OrderSerializer(serializers.ModelSerializer):
    """订单详情和列表响应。"""

    buyer = serializers.SerializerMethodField()
    seller = serializers.SerializerMethodField()
    listing = OrderListingSerializer(read_only=True, allow_null=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    viewer_role = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "buyer",
            "seller",
            "listing",
            "buyer_display_name",
            "seller_display_name",
            "listing_title_snapshot",
            "status",
            "status_display",
            "order_price",
            "payment_deadline",
            "paid_at",
            "shipped_at",
            "logistics_signed_due_at",
            "signed_at",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "viewer_role",
            "is_expired",
            "available_actions",
        ]

    def get_viewer_role(self, obj):
        request = self.context.get("request")
        return get_order_viewer_role(obj, getattr(request, "user", None))

    def get_buyer(self, obj):
        if obj.buyer is None:
            return None
        return OrderUserSerializer(obj.buyer).data

    def get_seller(self, obj):
        if obj.seller is None:
            return None
        return OrderUserSerializer(obj.seller).data

    def get_is_expired(self, obj):
        return is_order_payment_expired(obj)

    def get_available_actions(self, obj):
        request = self.context.get("request")
        return get_order_available_actions(obj, getattr(request, "user", None))

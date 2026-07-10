"""orders 应用 API 路由。"""

from django.urls import path

from orders.views import (
    BuyerOrderListApiView,
    ListingOrderCreateApiView,
    OrderConfirmDeliveryApiView,
    OrderConfirmReceiptApiView,
    OrderDetailApiView,
    OrderPayApiView,
    OrderRatingApiView,
    SellerOrderListApiView,
)

urlpatterns = [
    path(
        "listings/<int:listing_id>/orders/",
        ListingOrderCreateApiView.as_view(),
        name="orders_create",
    ),
    path("orders/buyer/", BuyerOrderListApiView.as_view(), name="orders_buyer"),
    path("orders/seller/", SellerOrderListApiView.as_view(), name="orders_seller"),
    path("orders/<int:pk>/", OrderDetailApiView.as_view(), name="orders_detail"),
    path("orders/<int:pk>/pay/", OrderPayApiView.as_view(), name="orders_pay"),
    path(
        "orders/<int:pk>/confirm-delivery/",
        OrderConfirmDeliveryApiView.as_view(),
        name="orders_confirm_delivery",
    ),
    path(
        "orders/<int:pk>/confirm-receipt/",
        OrderConfirmReceiptApiView.as_view(),
        name="orders_confirm_receipt",
    ),
    path(
        "orders/<int:pk>/rating/",
        OrderRatingApiView.as_view(),
        name="orders_rating",
    ),
]


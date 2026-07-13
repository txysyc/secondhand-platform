"""orders 应用 API 路由。"""

from django.urls import path

from orders.views import (
    BuyerOrderListAPIView,
    ListingOrderCreateAPIView,
    OrderConfirmDeliveryAPIView,
    OrderConfirmReceiptAPIView,
    OrderDetailAPIView,
    OrderPayAPIView,
    OrderRatingAPIView,
    SellerOrderListAPIView,
)

urlpatterns = [
    path(
        "listings/<int:listing_id>/orders/",
        ListingOrderCreateAPIView.as_view(),
        name="orders_create",
    ),
    path("orders/buyer/", BuyerOrderListAPIView.as_view(), name="orders_buyer"),
    path("orders/seller/", SellerOrderListAPIView.as_view(), name="orders_seller"),
    path("orders/<int:pk>/", OrderDetailAPIView.as_view(), name="orders_detail"),
    path("orders/<int:pk>/pay/", OrderPayAPIView.as_view(), name="orders_pay"),
    path(
        "orders/<int:pk>/confirm-delivery/",
        OrderConfirmDeliveryAPIView.as_view(),
        name="orders_confirm_delivery",
    ),
    path(
        "orders/<int:pk>/confirm-receipt/",
        OrderConfirmReceiptAPIView.as_view(),
        name="orders_confirm_receipt",
    ),
    path(
        "orders/<int:pk>/rating/",
        OrderRatingAPIView.as_view(),
        name="orders_rating",
    ),
]


from django.urls import path

from orders.views import (
    OrderDetailView,
    OrderPayView,
    BuyerOrderListView,
    SellerOrderListView,
    OrderConfirmDeliveryView,
    OrderConfirmReceiptView,
)

app_name = "orders"

urlpatterns = [
    path("buying/", BuyerOrderListView.as_view(), name="buyer_order_list"),
    path("selling/", SellerOrderListView.as_view(), name="seller_order_list"),
    path("<int:pk>/", OrderDetailView.as_view(), name="order_detail"),
    path("<int:pk>/pay/", OrderPayView.as_view(), name="order_pay"),
    path(
        "<int:pk>/confirm-delivery",
        OrderConfirmDeliveryView.as_view(),
        name="confirm_delivery",
    ),
    path(
        "<int:pk>/confirm-receipt",
        OrderConfirmReceiptView.as_view(),
        name="order_confirm_receipt",
    ),
]

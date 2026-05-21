from django.urls import path

from orders.views import OrderDetailView, OrderPayView

app_name = "orders"

urlpatterns = [
    path("<int:pk>/", OrderDetailView.as_view(), name="order_detail"),
    path("<int:pk>/pay/", OrderPayView.as_view(), name="order_pay"),
]

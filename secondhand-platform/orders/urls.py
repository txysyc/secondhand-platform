from django.urls import path

from orders.views import OrderDetailView

app_name = "orders"

urlpatterns = [path("<int:pk>/", OrderDetailView.as_view(), name="order_detail")]

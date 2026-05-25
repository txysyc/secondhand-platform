from typing import Any

from django.db.models.query import QuerySet
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
from django.utils import timezone
from django.views.generic import ListView

from orders.models import Order
from orders.services import pay_order, confirm_order_delivery, confirm_order_receipt
from orders.selectors import get_buyer_orders, get_seller_orders


class OrderDetailView(LoginRequiredMixin, View):
    template_name = "orders/order_detail.html"

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if request.user != order.buyer and request.user != order.seller:
            raise Http404
        viewer_role = "buyer" if request.user == order.buyer else "seller"
        is_expired = (
            order.status == Order.OrderStatus.PENDING_PAYMENT
            and order.payment_deadline < timezone.now()
        )
        context = {
            "order": order,
            "is_expired": is_expired,
            "viewer_role": viewer_role,
        }
        return render(request, self.template_name, context)


class OrderPayView(LoginRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(Order, pk=pk)
        try:
            pay_order(request.user, pk)
        except PermissionDenied:
            messages.error(request, "当前用户不是订单买家，无权进行支付")
        except ValidationError as e:
            messages.error(request, e.message)
        else:
            messages.success(request, "完成支付")

        return redirect("orders:order_detail", pk)


class BuyerOrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = "orders/buyer_order_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Any]:
        return get_buyer_orders(self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["now"] = timezone.now()
        return context


class SellerOrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = "orders/seller_order_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self) -> QuerySet[Any]:
        return get_seller_orders(self.request.user)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["now"] = timezone.now()
        return context


class OrderConfirmDeliveryView(LoginRequiredMixin, View):
    model = Order

    def post(self, request, pk):
        try:
            confirm_order_delivery(request.user, pk)
        except ValidationError as e:
            messages.error(request, e.messages)
            return redirect("orders:order_detail", pk)

        messages.success(request, "已确认发货")
        return redirect("orders:order_detail", pk)


class OrderConfirmReceiptView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            confirm_order_receipt(request.user, pk)
        except ValidationError as e:
            messages.error(request, e.messages)
            return redirect("orders:order_detail", pk)

        messages.success(request, "已确认收货，交易完成")
        return redirect("orders:order_detail", pk)

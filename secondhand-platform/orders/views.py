from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages
from django.utils import timezone

from orders.models import Order
from orders.services import pay_order


class OrderDetailView(LoginRequiredMixin, View):
    template_name = "orders/order_detail.html"

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if request.user != order.buyer and request.user != order.seller:
            raise Http404
        is_expired = (
            order.status == Order.OrderStatus.PENDING_PAYMENT
            and order.payment_deadline < timezone.now()
        )
        context = {"order": order, "is_expired": is_expired}
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

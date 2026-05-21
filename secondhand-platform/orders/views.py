from django.http import Http404
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from orders.models import Order


class OrderDetailView(LoginRequiredMixin, View):
    template_name = "orders/order_detail.html"

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if request.user != order.buyer and request.user != order.seller:
            raise Http404
        context = {"order": order}
        return render(request, self.template_name, context)

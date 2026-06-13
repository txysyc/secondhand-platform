"""orders 应用 API 类视图。"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Listing
from orders.api.permissions import IsOrderParticipant
from orders.api.serializers import OrderSerializer
from orders.selectors import get_buyer_orders, get_order_queryset, get_seller_orders
from orders.services import (
    confirm_order_delivery,
    confirm_order_receipt,
    create_order,
    pay_order,
)


class _ServiceErrorMixin:
    """把服务层异常转成稳定的 DRF 错误响应。"""

    def run_service(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DjangoValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else "请求处理失败"
            raise ValidationError(detail=message)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(detail=str(exc))


class _OrderPaginatorMixin:
    """订单列表分页辅助。"""

    page_size = 20

    def paginate(self, request, queryset):
        page_number = request.query_params.get("page", 1)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1

        page_number = max(page_number, 1)
        total = queryset.count()
        start = (page_number - 1) * self.page_size
        end = start + self.page_size
        items = list(queryset[start:end])
        next_page = page_number + 1 if end < total else None
        previous_page = page_number - 1 if page_number > 1 else None
        return Response(
            {
                "count": total,
                "next": None if next_page is None else self._page_url(request, next_page),
                "previous": (
                    None
                    if previous_page is None
                    else self._page_url(request, previous_page)
                ),
                "results": OrderSerializer(
                    items,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )

    def _page_url(self, request, page_number):
        query_params = request.query_params.copy()
        query_params["page"] = page_number
        return f"{request.build_absolute_uri(request.path)}?{query_params.urlencode()}"


class ListingOrderCreateApiView(_ServiceErrorMixin, APIView):
    """为指定商品创建待支付订单。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        listing = get_object_or_404(
            Listing.objects.select_related("owner", "owner__profile"),
            pk=listing_id,
        )
        order = self.run_service(create_order, request.user, listing)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BuyerOrderListApiView(_OrderPaginatorMixin, APIView):
    """当前用户买家订单列表。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return self.paginate(request, get_buyer_orders(request.user))


class SellerOrderListApiView(_OrderPaginatorMixin, APIView):
    """当前用户卖家订单列表。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return self.paginate(request, get_seller_orders(request.user))


class _OrderParticipantApiView(_ServiceErrorMixin, APIView):
    """需要订单参与者身份的 API 基类。"""

    permission_classes = [IsAuthenticated, IsOrderParticipant]

    def get_object(self, request, pk):
        order = get_object_or_404(get_order_queryset(), pk=pk)
        self.check_object_permissions(request, order)
        return order


class OrderDetailApiView(_OrderParticipantApiView):
    """订单详情。"""

    def get(self, request, pk):
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderPayApiView(_OrderParticipantApiView):
    """买家模拟支付。"""

    def post(self, request, pk):
        self.get_object(request, pk)
        order = self.run_service(pay_order, request.user, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderConfirmDeliveryApiView(_OrderParticipantApiView):
    """卖家确认发货或交付。"""

    def post(self, request, pk):
        self.get_object(request, pk)
        self.run_service(confirm_order_delivery, request.user, pk)
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderConfirmReceiptApiView(_OrderParticipantApiView):
    """买家确认收货。"""

    def post(self, request, pk):
        self.get_object(request, pk)
        self.run_service(confirm_order_receipt, request.user, pk)
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)

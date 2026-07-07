"""orders 应用 API 类视图。"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import PageNumberPaginationMixin
from catalog.models import Listing
from orders.permissions import IsOrderParticipant
from orders.serializers import OrderSerializer
from orders.selectors import get_buyer_orders, get_order_queryset, get_seller_orders
from orders.services import (
    confirm_order_delivery,
    confirm_order_receipt,
    create_order,
    pay_order,
)


class ListingOrderCreateApiView(APIView):
    """为指定商品创建待支付订单。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        listing = get_object_or_404(
            Listing.objects.select_related("owner", "owner__profile"),
            pk=listing_id,
        )
        order = create_order(request.user, listing)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BuyerOrderListApiView(PageNumberPaginationMixin, APIView):
    """当前用户买家订单列表。"""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get(self, request):
        return self.paginate(request, get_buyer_orders(request.user))


class SellerOrderListApiView(PageNumberPaginationMixin, APIView):
    """当前用户卖家订单列表。"""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get(self, request):
        return self.paginate(request, get_seller_orders(request.user))


class _OrderParticipantApiView(APIView):
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
        # 先做参与者权限校验，再进入服务层加锁处理支付状态流转。
        self.get_object(request, pk)
        order = pay_order(request.user, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderConfirmDeliveryApiView(_OrderParticipantApiView):
    """卖家确认发货或交付。"""

    def post(self, request, pk):
        # 服务层会重新锁定订单和商品；这里的读取只负责 API 权限门禁。
        self.get_object(request, pk)
        confirm_order_delivery(request.user, pk)
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderConfirmReceiptApiView(_OrderParticipantApiView):
    """买家确认收货。"""

    def post(self, request, pk):
        # 服务层会重新锁定订单和商品；这里的读取只负责 API 权限门禁。
        self.get_object(request, pk)
        confirm_order_receipt(request.user, pk)
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


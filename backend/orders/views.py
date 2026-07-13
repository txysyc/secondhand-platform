"""orders 应用 API 类视图。"""

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import PageNumberPaginationMixin
from catalog.models import Listing
from orders.filters import OrderFilterSet
from orders.permissions import IsOrderParticipant
from orders.serializers import OrderRatingWriteSerializer, OrderSerializer
from orders.selectors import (
    apply_order_list_sort,
    get_buyer_orders,
    get_order_queryset,
    get_seller_orders,
)
from orders.services import (
    confirm_order_delivery,
    confirm_order_receipt,
    create_order,
    create_order_rating,
    pay_order,
)


class OrderCreationConflict(APIException):
    """订单创建幂等处理中冲突。"""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "订单正在创建中，请勿重复提交"
    default_code = "order_creation_conflict"


class ListingOrderCreateAPIView(APIView):
    """为指定商品创建待支付订单。"""

    permission_classes = [IsAuthenticated]
    throttle_scope = "order_create"
    idempotency_ttl_seconds = 15 * 60

    def _validate_idempotency_key(self, request):
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise ValidationError("缺少幂等请求头")
        if len(idempotency_key) < 8 or len(idempotency_key) > 128:
            raise ValidationError("幂等请求头长度必须为8到128个字符")
        return idempotency_key

    def post(self, request, listing_id):
        idempotency_key = self._validate_idempotency_key(request)
        cache_key = (
            f"order:idempotency:{request.user.id}:{listing_id}:{idempotency_key}"
        )

        cached_value = cache.get(cache_key)
        if cached_value == "processing":
            raise OrderCreationConflict()
        if cached_value:
            order = get_object_or_404(get_order_queryset(), pk=cached_value)
            serializer = OrderSerializer(order, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        is_processing_mark_created = cache.add(
            cache_key,
            "processing",
            timeout=self.idempotency_ttl_seconds,
        )
        if not is_processing_mark_created:
            raise OrderCreationConflict()

        listing = get_object_or_404(
            Listing.objects.select_related("owner", "owner__profile"),
            pk=listing_id,
        )
        try:
            order = create_order(
                request.user,
                listing,
                address_id=request.data.get("address_id"),
            )
        except Exception:
            cache.delete(cache_key)
            raise

        cache.set(cache_key, order.pk, timeout=self.idempotency_ttl_seconds)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BuyerOrderListAPIView(PageNumberPaginationMixin, APIView):
    """当前用户买家订单列表。"""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    max_page_size = 50

    def get(self, request):
        queryset = _filter_and_sort_orders(request, get_buyer_orders(request.user))
        return self.paginate(request, queryset)


class SellerOrderListAPIView(PageNumberPaginationMixin, APIView):
    """当前用户卖家订单列表。"""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    max_page_size = 50

    def get(self, request):
        queryset = _filter_and_sort_orders(request, get_seller_orders(request.user))
        return self.paginate(request, queryset)


def _filter_and_sort_orders(request, queryset):
    """校验订单列表筛选参数，并按白名单排序返回 QuerySet。"""

    filterset = OrderFilterSet(data=request.query_params, queryset=queryset)
    if not filterset.is_valid():
        raise ValidationError(filterset.errors)
    return apply_order_list_sort(filterset.qs, request.query_params.get("sort"))


class _OrderParticipantAPIView(APIView):
    """需要订单参与者身份的 API 基类。"""

    permission_classes = [IsAuthenticated, IsOrderParticipant]

    def get_object(self, request, pk):
        order = get_object_or_404(get_order_queryset(), pk=pk)
        self.check_object_permissions(request, order)
        return order


class OrderDetailAPIView(_OrderParticipantAPIView):
    """订单详情。"""

    def get(self, request, pk):
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderPayAPIView(_OrderParticipantAPIView):
    """买家模拟支付。"""

    def post(self, request, pk):
        # 先做参与者权限校验，再进入服务层加锁处理支付状态流转。
        self.get_object(request, pk)
        order = pay_order(request.user, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderConfirmDeliveryAPIView(_OrderParticipantAPIView):
    """卖家确认发货或交付。"""

    def post(self, request, pk):
        # 服务层会重新锁定订单和商品；这里的读取只负责 API 权限门禁。
        self.get_object(request, pk)
        confirm_order_delivery(request.user, pk)
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderConfirmReceiptAPIView(_OrderParticipantAPIView):
    """买家确认收货。"""

    def post(self, request, pk):
        # 服务层会重新锁定订单和商品；这里的读取只负责 API 权限门禁。
        self.get_object(request, pk)
        confirm_order_receipt(request.user, pk)
        order = self.get_object(request, pk)
        serializer = OrderSerializer(order, context={"request": request})
        return Response(serializer.data)


class OrderRatingAPIView(_OrderParticipantAPIView):
    """买家为已完成订单提交一次星级评分。"""

    throttle_scope = "rating_write"

    def post(self, request, pk):
        # 先复用订单参与者权限门禁，再由服务层校验买家身份和订单完成状态。
        self.get_object(request, pk)
        serializer = OrderRatingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _, created = create_order_rating(
            request.user,
            pk,
            serializer.validated_data["score"],
        )
        order = self.get_object(request, pk)
        response_serializer = OrderSerializer(order, context={"request": request})
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


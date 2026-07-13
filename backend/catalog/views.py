"""catalog 应用 API 类视图。"""

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import PageNumberPaginationMixin
from api.throttles import MethodScopedThrottleMixin
from catalog.cache import get_active_category_payload, get_cached_public_listing_detail
from catalog.filters import ListingFilterSet, MyListingFilterSet
from catalog.permissions import IsListingOwner
from catalog.serializers import (
    CategorySerializer,
    ListingDetailSerializer,
    ListingImageReorderSerializer,
    ListingImageUploadSerializer,
    ListingWriteSerializer,
)
from catalog.models import Listing
from catalog.selectors import (
    apply_owner_listing_sort,
    apply_public_listing_sort,
    get_active_categories,
    get_owner_listing_queryset,
    get_public_listing_detail_queryset,
    get_public_listing_queryset,
    get_visible_listing_detail_queryset,
)
from catalog.services import (
    add_listing_images,
    change_listing_status_for_user,
    create_listing_from_payload,
    delete_listing_for_user,
    delete_listing_image,
    publish_listing_for_user,
    reorder_listing_images,
    update_listing_from_payload,
)
from interactions.selectors import annotate_listings_with_favorite_status
from interactions.services import record_listing_view


class CategoryListAPIView(APIView):
    """启用分类列表。"""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_active_category_payload())


class ListingListAPIView(PageNumberPaginationMixin, APIView):
    """公开商品列表。"""

    permission_classes = [AllowAny]
    max_page_size = 50

    def get(self, request):
        queryset = get_public_listing_queryset()
        queryset = annotate_listings_with_favorite_status(queryset, request.user)
        filterset = ListingFilterSet(data=request.query_params, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)
        queryset = apply_public_listing_sort(
            filterset.qs,
            request.query_params.get("sort"),
        )
        return self.paginate(request, queryset, ListingDetailSerializer)


class ListingDetailAPIView(APIView):
    """商品详情。

    在售商品公开可见；支付后只有交易买家和卖家能继续查看详情。
    """

    permission_classes = [AllowAny]

    def get_object(self, request, pk):
        queryset = annotate_listings_with_favorite_status(
            get_visible_listing_detail_queryset(request.user),
            request.user,
        )
        return get_object_or_404(
            queryset,
            pk=pk,
        )

    def get(self, request, pk):
        if not request.user.is_authenticated:
            payload = get_cached_public_listing_detail(
                pk,
                lambda: self._build_public_detail_payload(pk, request),
            )
            if payload is None:
                raise Http404("商品不存在或暂不可见")
            return Response(payload)

        listing = self.get_object(request, pk)
        record_listing_view(request.user, listing)
        serializer = ListingDetailSerializer(listing, context={"request": request})
        return Response(serializer.data)

    def _build_public_detail_payload(self, pk, request):
        """构建仅供匿名访客复用的公开商品详情快照。"""

        listing = get_public_listing_detail_queryset().filter(pk=pk).first()
        if listing is None:
            return None
        return ListingDetailSerializer(listing, context={"request": request}).data


class MyListingListCreateAPIView(MethodScopedThrottleMixin, PageNumberPaginationMixin, APIView):
    """当前用户商品列表与草稿创建。"""

    permission_classes = [IsAuthenticated]
    method_throttle_scopes = {"POST": "listing_write"}
    max_page_size = 50

    def get(self, request):
        queryset = get_owner_listing_queryset(request.user)
        queryset = annotate_listings_with_favorite_status(queryset, request.user)
        filterset = MyListingFilterSet(data=request.query_params, queryset=queryset)
        if not filterset.is_valid():
            raise ValidationError(filterset.errors)
        queryset = apply_owner_listing_sort(
            filterset.qs,
            request.query_params.get("sort"),
        )
        return self.paginate(request, queryset, ListingDetailSerializer)

    def post(self, request):
        serializer = ListingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing = create_listing_from_payload(
            request.user,
            serializer.validated_data,
        )
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class _OwnedListingAPIView(APIView):
    """带所有权校验的商品基类视图。"""

    permission_classes = [IsAuthenticated, IsListingOwner]

    def get_object(self, request, pk):
        queryset = (
            Listing.objects.select_related("category", "owner", "owner__profile")
            .prefetch_related("images")
        )
        queryset = annotate_listings_with_favorite_status(queryset, request.user)
        listing = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(request, listing)
        return listing

    def get_fresh_object(self, request, pk):
        return self.get_object(request, pk)


class MyListingDetailAPIView(_OwnedListingAPIView):
    """更新或删除自己的商品。"""

    def get(self, request, pk):
        listing = self.get_object(request, pk)
        serializer = ListingDetailSerializer(listing, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, pk):
        listing = self.get_object(request, pk)
        serializer = ListingWriteSerializer(
            listing,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        listing = update_listing_from_payload(
            request.user,
            listing,
            serializer.validated_data,
        )
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)

    def delete(self, request, pk):
        listing = self.get_object(request, pk)
        delete_listing_for_user(request.user, listing)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListingPublishAPIView(_OwnedListingAPIView):
    """发布自己的草稿商品。"""

    throttle_scope = "listing_write"

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        listing = publish_listing_for_user(request.user, listing)
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)


class ListingDeactivateAPIView(_OwnedListingAPIView):
    """下架自己的在售商品。"""

    throttle_scope = "listing_write"

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        listing = change_listing_status_for_user(
            request.user,
            listing,
            "withdraw",
        )
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)


class ListingReactivateAPIView(_OwnedListingAPIView):
    """重新上架自己的已下架商品。"""

    throttle_scope = "listing_write"

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        listing = change_listing_status_for_user(
            request.user,
            listing,
            "restore_active",
        )
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)


class ListingImageUploadAPIView(_OwnedListingAPIView):
    """上传商品图片。"""

    throttle_scope = "image_upload"

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        images = request.FILES.getlist("images") or request.FILES.getlist("image")
        serializer = ListingImageUploadSerializer(data={"images": images})
        serializer.is_valid(raise_exception=True)
        add_listing_images(
            request.user,
            listing,
            serializer.validated_data["images"],
        )
        listing = self.get_fresh_object(request, pk)
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ListingImageDeleteAPIView(_OwnedListingAPIView):
    """删除商品图片。"""

    def delete(self, request, pk, image_id):
        listing = self.get_object(request, pk)
        delete_listing_image(request.user, listing, image_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListingImageReorderAPIView(_OwnedListingAPIView):
    """重排商品图片。"""

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        serializer = ListingImageReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reorder_listing_images(
            request.user,
            listing,
            serializer.validated_data["image_ids"],
        )
        listing = self.get_fresh_object(request, pk)
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)


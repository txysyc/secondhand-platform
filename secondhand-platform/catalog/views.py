"""catalog 应用 API 类视图。"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api_mixins import PageNumberPaginationMixin, ServiceErrorMixin
from catalog.permissions import IsListingOwner
from catalog.serializers import (
    CategorySerializer,
    ListingDetailSerializer,
    ListingFilterSerializer,
    ListingImageReorderSerializer,
    ListingImageUploadSerializer,
    ListingWriteSerializer,
)
from catalog.models import Listing
from catalog.selectors import (
    get_active_categories,
    get_owner_listing_queryset,
    get_public_listing_detail_queryset,
    get_public_listing_queryset,
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


class CategoryListApiView(APIView):
    """启用分类列表。"""

    permission_classes = [AllowAny]

    def get(self, request):
        serializer = CategorySerializer(get_active_categories(), many=True)
        return Response(serializer.data)


class ListingListApiView(PageNumberPaginationMixin, APIView):
    """公开商品列表。"""

    permission_classes = [AllowAny]

    def get(self, request):
        serializer = ListingFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = get_public_listing_queryset(serializer.validated_data)
        return self.paginate(request, queryset, ListingDetailSerializer)


class ListingDetailApiView(APIView):
    """公开商品详情。"""

    permission_classes = [AllowAny]

    def get_object(self, pk):
        return get_object_or_404(get_public_listing_detail_queryset(), pk=pk)

    def get(self, request, pk):
        listing = self.get_object(pk)
        serializer = ListingDetailSerializer(listing, context={"request": request})
        return Response(serializer.data)


class MyListingListCreateApiView(
    ServiceErrorMixin,
    PageNumberPaginationMixin,
    APIView,
):
    """当前用户商品列表与草稿创建。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = get_owner_listing_queryset(request.user)
        return self.paginate(request, queryset, ListingDetailSerializer)

    def post(self, request):
        serializer = ListingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing = self.run_service(
            create_listing_from_payload,
            request.user,
            serializer.validated_data,
        )
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class _OwnedListingAPIView(ServiceErrorMixin, APIView):
    """带所有权校验的商品基类视图。"""

    permission_classes = [IsAuthenticated, IsListingOwner]

    def get_object(self, request, pk):
        queryset = (
            Listing.objects.select_related("category", "owner", "owner__profile")
            .prefetch_related("images")
        )
        listing = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(request, listing)
        return listing

    def get_fresh_object(self, request, pk):
        return self.get_object(request, pk)


class MyListingDetailApiView(_OwnedListingAPIView):
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
        listing = self.run_service(
            update_listing_from_payload,
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
        self.run_service(delete_listing_for_user, request.user, listing)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListingPublishApiView(_OwnedListingAPIView):
    """发布自己的草稿商品。"""

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        listing = self.run_service(publish_listing_for_user, request.user, listing)
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)


class ListingDeactivateApiView(_OwnedListingAPIView):
    """下架自己的在售商品。"""

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        listing = self.run_service(
            change_listing_status_for_user,
            request.user,
            listing,
            "withdraw",
        )
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)


class ListingReactivateApiView(_OwnedListingAPIView):
    """重新上架自己的已下架商品。"""

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        listing = self.run_service(
            change_listing_status_for_user,
            request.user,
            listing,
            "restore_active",
        )
        response_serializer = ListingDetailSerializer(
            listing,
            context={"request": request},
        )
        return Response(response_serializer.data)


class ListingImageUploadApiView(_OwnedListingAPIView):
    """上传商品图片。"""

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        images = request.FILES.getlist("images") or request.FILES.getlist("image")
        serializer = ListingImageUploadSerializer(data={"images": images})
        serializer.is_valid(raise_exception=True)
        self.run_service(
            add_listing_images,
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


class ListingImageDeleteApiView(_OwnedListingAPIView):
    """删除商品图片。"""

    def delete(self, request, pk, image_id):
        listing = self.get_object(request, pk)
        self.run_service(delete_listing_image, request.user, listing, image_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListingImageReorderApiView(_OwnedListingAPIView):
    """重排商品图片。"""

    def post(self, request, pk):
        listing = self.get_object(request, pk)
        serializer = ListingImageReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.run_service(
            reorder_listing_images,
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


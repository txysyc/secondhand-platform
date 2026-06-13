"""catalog 应用 API 类视图。"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.api.permissions import IsListingOwner
from catalog.api.serializers import (
    CategorySerializer,
    ListingDetailSerializer,
    ListingFilterSerializer,
    ListingImageReorderSerializer,
    ListingImageUploadSerializer,
    ListingWriteSerializer,
)
from catalog.models import Listing
from catalog.selectors import get_active_categories, get_publish_listing_queryset
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


class _ListingPaginatorMixin:
    """商品列表分页辅助。"""

    page_size = 20

    def paginate(self, request, queryset, serializer_class):
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
                "results": serializer_class(items, many=True, context={"request": request}).data,
            }
        )

    def _page_url(self, request, page_number):
        query_params = request.query_params.copy()
        query_params["page"] = page_number
        return f"{request.build_absolute_uri(request.path)}?{query_params.urlencode()}"


class _ServiceErrorMixin:
    """把 Django 异常转成 DRF 异常，保证 API 返回稳定 JSON。"""

    def run_service(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DjangoValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else "请求处理失败"
            raise ValidationError(detail=message)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(detail=str(exc))


class ListingListApiView(_ListingPaginatorMixin, APIView):
    """公开商品列表。"""

    permission_classes = [AllowAny]

    def get(self, request):
        serializer = ListingFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = get_publish_listing_queryset(serializer.validated_data)
        return self.paginate(request, queryset, ListingDetailSerializer)


class ListingDetailApiView(APIView):
    """公开商品详情。"""

    permission_classes = [AllowAny]

    def get_object(self, pk):
        queryset = (
            Listing.objects.select_related("category", "owner", "owner__profile")
            .prefetch_related("images")
            .filter(status=Listing.Status.ACTIVE, category__is_active=True)
        )
        return get_object_or_404(queryset, pk=pk)

    def get(self, request, pk):
        listing = self.get_object(pk)
        serializer = ListingDetailSerializer(listing, context={"request": request})
        return Response(serializer.data)


class MyListingListCreateApiView(_ServiceErrorMixin, _ListingPaginatorMixin, APIView):
    """当前用户商品列表与草稿创建。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = (
            Listing.objects.filter(owner=request.user)
            .select_related("category", "owner", "owner__profile")
            .prefetch_related("images")
            .order_by("-updated_at", "-id")
        )
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


class _OwnedListingAPIView(_ServiceErrorMixin, APIView):
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

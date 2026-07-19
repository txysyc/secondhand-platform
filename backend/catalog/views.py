"""catalog 应用 API 通用视图。"""

from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.throttles import MethodScopedThrottleMixin
from catalog.cache import get_active_category_payload, get_cached_public_listing_detail
from catalog.filters import (
    ListingFilterSet,
    ListingOrderingFilter,
    ListingSearchFilter,
    MyListingFilterSet,
)
from catalog.models import Listing
from catalog.permissions import IsListingOwner
from catalog.serializers import (
    ListingDetailSerializer,
    ListingImageReorderSerializer,
    ListingImageUploadSerializer,
    ListingWriteSerializer,
)
from catalog.selectors import (
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


LISTING_FILTER_BACKENDS = (
    DjangoFilterBackend,
    ListingSearchFilter,
    ListingOrderingFilter,
)
LISTING_SEARCH_FIELDS = ("title", "description")


def _listing_response(listing, request, *, status_code=status.HTTP_200_OK):
    """使用详情 serializer 返回商品，统一 request context。"""

    serializer = ListingDetailSerializer(listing, context={"request": request})
    return Response(serializer.data, status=status_code)


class CategoryListAPIView(GenericAPIView):
    """启用的分类列表。"""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(get_active_category_payload())


class ListingListAPIView(ListAPIView):
    """公开商品列表。"""

    permission_classes = [AllowAny]
    serializer_class = ListingDetailSerializer
    filter_backends = LISTING_FILTER_BACKENDS
    filterset_class = ListingFilterSet
    search_fields = LISTING_SEARCH_FIELDS
    ordering = ("-published_at", "-id")
    ordering_aliases = {
        "oldest": ("published_at", "id"),
        "price_asc": ("price", "id"),
        "price_desc": ("-price", "-id"),
    }

    def get_queryset(self):
        return annotate_listings_with_favorite_status(
            get_public_listing_queryset(),
            self.request.user,
        )


class ListingDetailAPIView(RetrieveAPIView):
    """商品详情。

    在售商品公开可见；支付后只有交易买家和卖家能继续查看详情。
    """

    permission_classes = [AllowAny]
    serializer_class = ListingDetailSerializer

    def get_queryset(self):
        queryset = get_visible_listing_detail_queryset(self.request.user)
        return annotate_listings_with_favorite_status(queryset, self.request.user)

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            payload = get_cached_public_listing_detail(
                kwargs["pk"],
                lambda: self._build_public_detail_payload(kwargs["pk"], request),
            )
            if payload is None:
                raise Http404("商品不存在或暂不可见")
            return Response(payload)

        listing = self.get_object()
        record_listing_view(request.user, listing)
        return _listing_response(listing, request)

    def _build_public_detail_payload(self, listing_id, request):
        """构建仅供匿名访客复用的公开商品详情快照。"""

        listing = get_public_listing_detail_queryset().filter(pk=listing_id).first()
        if listing is None:
            return None
        return ListingDetailSerializer(listing, context={"request": request}).data


class MyListingListCreateAPIView(
    MethodScopedThrottleMixin,
    ListCreateAPIView,
):
    """当前用户商品列表与草稿创建。"""

    permission_classes = [IsAuthenticated]
    method_throttle_scopes = {"POST": "listing_write"}
    serializer_class = ListingDetailSerializer
    filter_backends = LISTING_FILTER_BACKENDS
    filterset_class = MyListingFilterSet
    search_fields = LISTING_SEARCH_FIELDS
    ordering = ("-updated_at", "-id")
    ordering_aliases = {
        "updated_asc": ("updated_at", "id"),
        "published_desc": ("-published_at", "-id"),
        "published_asc": ("published_at", "id"),
        "price_asc": ("price", "id"),
        "price_desc": ("-price", "-id"),
    }

    def get_queryset(self):
        return annotate_listings_with_favorite_status(
            get_owner_listing_queryset(self.request.user),
            self.request.user,
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ListingWriteSerializer
        return ListingDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing = create_listing_from_payload(request.user, serializer.validated_data)
        return _listing_response(
            listing,
            request,
            status_code=status.HTTP_201_CREATED,
        )


class _OwnedListingMixin:
    """提供所有者查询集和对象刷新逻辑。"""

    permission_classes = [IsAuthenticated, IsListingOwner]

    def get_queryset(self):
        queryset = Listing.objects.select_related(
            "category", "owner", "owner__profile"
        ).prefetch_related("images")
        return annotate_listings_with_favorite_status(queryset, self.request.user)

    def get_fresh_object(self):
        return self.get_object()


class MyListingDetailAPIView(
    _OwnedListingMixin,
    RetrieveUpdateDestroyAPIView,
):
    """更新或删除自己的商品。"""

    serializer_class = ListingDetailSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        listing = self.get_object()
        serializer = ListingWriteSerializer(
            listing,
            data=request.data,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        listing = update_listing_from_payload(
            request.user,
            listing,
            serializer.validated_data,
        )
        return _listing_response(listing, request)

    def perform_destroy(self, instance):
        delete_listing_for_user(self.request.user, instance)


class ListingPublishAPIView(_OwnedListingMixin, GenericAPIView):
    """发布自己的草稿商品。"""

    throttle_scope = "listing_write"

    def post(self, request, pk):
        listing = publish_listing_for_user(request.user, self.get_object())
        return _listing_response(listing, request)


class ListingDeactivateAPIView(_OwnedListingMixin, GenericAPIView):
    """下架自己的在售商品。"""

    throttle_scope = "listing_write"

    def post(self, request, pk):
        listing = change_listing_status_for_user(
            request.user,
            self.get_object(),
            "withdraw",
        )
        return _listing_response(listing, request)


class ListingReactivateAPIView(_OwnedListingMixin, GenericAPIView):
    """重新上架自己的已下架商品。"""

    throttle_scope = "listing_write"

    def post(self, request, pk):
        listing = change_listing_status_for_user(
            request.user,
            self.get_object(),
            "restore_active",
        )
        return _listing_response(listing, request)


class ListingImageUploadAPIView(_OwnedListingMixin, GenericAPIView):
    """上传商品图片。"""

    throttle_scope = "image_upload"

    def post(self, request, pk):
        listing = self.get_object()
        images = request.FILES.getlist("images") or request.FILES.getlist("image")
        serializer = ListingImageUploadSerializer(data={"images": images})
        serializer.is_valid(raise_exception=True)
        add_listing_images(
            request.user,
            listing,
            serializer.validated_data["images"],
        )
        return _listing_response(
            self.get_fresh_object(),
            request,
            status_code=status.HTTP_201_CREATED,
        )


class ListingImageDeleteAPIView(_OwnedListingMixin, GenericAPIView):
    """删除商品图片。"""

    def delete(self, request, pk, image_id):
        delete_listing_image(request.user, self.get_object(), image_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListingImageReorderAPIView(_OwnedListingMixin, GenericAPIView):
    """重排商品图片。"""

    def post(self, request, pk):
        listing = self.get_object()
        serializer = ListingImageReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reorder_listing_images(
            request.user,
            listing,
            serializer.validated_data["image_ids"],
        )
        return _listing_response(self.get_fresh_object(), request)

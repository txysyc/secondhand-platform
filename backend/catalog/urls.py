"""catalog 应用 API 路由。"""

from django.urls import path

from catalog.views import (
    CategoryListAPIView,
    ListingImageDeleteAPIView,
    ListingImageReorderAPIView,
    ListingImageUploadAPIView,
    ListingPublishAPIView,
    ListingDeactivateAPIView,
    ListingListAPIView,
    ListingDetailAPIView,
    MyListingDetailAPIView,
    MyListingListCreateAPIView,
    ListingReactivateAPIView,
)

urlpatterns = [
    path("categories/", CategoryListAPIView.as_view(), name="catalog_categories"),
    path("listings/", ListingListAPIView.as_view(), name="catalog_listings"),
    path("listings/<int:pk>/", ListingDetailAPIView.as_view(), name="catalog_listing_detail"),
    path("my/listings/", MyListingListCreateAPIView.as_view(), name="catalog_my_listings"),
    path(
        "my/listings/<int:pk>/",
        MyListingDetailAPIView.as_view(),
        name="catalog_my_listing_detail",
    ),
    path(
        "my/listings/<int:pk>/publish/",
        ListingPublishAPIView.as_view(),
        name="catalog_my_listing_publish",
    ),
    path(
        "my/listings/<int:pk>/deactivate/",
        ListingDeactivateAPIView.as_view(),
        name="catalog_my_listing_deactivate",
    ),
    path(
        "my/listings/<int:pk>/reactivate/",
        ListingReactivateAPIView.as_view(),
        name="catalog_my_listing_reactivate",
    ),
    path(
        "my/listings/<int:pk>/images/",
        ListingImageUploadAPIView.as_view(),
        name="catalog_my_listing_images_upload",
    ),
    path(
        "my/listings/<int:pk>/images/<int:image_id>/",
        ListingImageDeleteAPIView.as_view(),
        name="catalog_my_listing_images_delete",
    ),
    path(
        "my/listings/<int:pk>/images/reorder/",
        ListingImageReorderAPIView.as_view(),
        name="catalog_my_listing_images_reorder",
    ),
]


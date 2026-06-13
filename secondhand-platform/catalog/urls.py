"""catalog 应用 API 路由。"""

from django.urls import path

from catalog.views import (
    CategoryListApiView,
    ListingImageDeleteApiView,
    ListingImageReorderApiView,
    ListingImageUploadApiView,
    ListingPublishApiView,
    ListingDeactivateApiView,
    ListingListApiView,
    ListingDetailApiView,
    MyListingDetailApiView,
    MyListingListCreateApiView,
    ListingReactivateApiView,
)

urlpatterns = [
    path("categories/", CategoryListApiView.as_view(), name="catalog_categories"),
    path("listings/", ListingListApiView.as_view(), name="catalog_listings"),
    path("listings/<int:pk>/", ListingDetailApiView.as_view(), name="catalog_listing_detail"),
    path("my/listings/", MyListingListCreateApiView.as_view(), name="catalog_my_listings"),
    path(
        "my/listings/<int:pk>/",
        MyListingDetailApiView.as_view(),
        name="catalog_my_listing_detail",
    ),
    path(
        "my/listings/<int:pk>/publish/",
        ListingPublishApiView.as_view(),
        name="catalog_my_listing_publish",
    ),
    path(
        "my/listings/<int:pk>/deactivate/",
        ListingDeactivateApiView.as_view(),
        name="catalog_my_listing_deactivate",
    ),
    path(
        "my/listings/<int:pk>/reactivate/",
        ListingReactivateApiView.as_view(),
        name="catalog_my_listing_reactivate",
    ),
    path(
        "my/listings/<int:pk>/images/",
        ListingImageUploadApiView.as_view(),
        name="catalog_my_listing_images_upload",
    ),
    path(
        "my/listings/<int:pk>/images/<int:image_id>/",
        ListingImageDeleteApiView.as_view(),
        name="catalog_my_listing_images_delete",
    ),
    path(
        "my/listings/<int:pk>/images/reorder/",
        ListingImageReorderApiView.as_view(),
        name="catalog_my_listing_images_reorder",
    ),
]


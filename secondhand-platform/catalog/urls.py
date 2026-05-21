from django.urls import path

from catalog.views import (
    ListingCreateView,
    ListingDeleteView,
    ListingStatusUpdateView,
    ListingUpdateView,
    MyListingListView,
    ListingListView,
    ListingDetailView,
    PurchaseConfirmView,
)

app_name = "catalog"

urlpatterns = [
    path("create/", ListingCreateView.as_view(), name="listing_create"),
    path("mine/", MyListingListView.as_view(), name="my_listing_list"),
    path("<int:pk>/edit/", ListingUpdateView.as_view(), name="listing_edit"),
    path("<int:pk>/delete/", ListingDeleteView.as_view(), name="listing_delete"),
    path(
        "<int:pk>/status/",
        ListingStatusUpdateView.as_view(),
        name="listing_status_update",
    ),
    path("", ListingListView.as_view(), name="listing_list"),
    path("<int:pk>/purchase/", PurchaseConfirmView.as_view(), name="listing_purchase"),
    path("<int:pk>/", ListingDetailView.as_view(), name="listing_detail"),
]

from django.urls import path

from catalog.views import (
    ListingCreateView,
    ListingDeleteView,
    ListingStatusUpdateView,
    ListingUpdateView,
    MyListingListView,
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
]

from django.urls import path

from catalog.views import ListingCreateView, ListingUpdateView, ListingDeleteView

app_name = "catalog"

urlpatterns = [
    path("create/", ListingCreateView.as_view(), name="listing_create"),
    path("<int:pk>/edit/", ListingUpdateView.as_view(), name="listing_edit"),
    path("<int:pk>/delete/", ListingDeleteView.as_view(), name="listing_delete"),
]

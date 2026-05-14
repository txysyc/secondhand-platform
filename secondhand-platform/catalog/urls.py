from django.urls import path, include

from catalog.views import ListingCreateView

app_name = "catalog"

urlpatterns = [path("create/", ListingCreateView.as_view(), name="listing_create")]

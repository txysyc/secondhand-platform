"""项目级 URL 配置。"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf.urls.static import static
from django.conf import settings
from users.views import PublicProfileView

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("users.urls", namespace="users")),
    path("users/<int:user_id>/", PublicProfileView.as_view(), name="public_profile"),
    path("listings/", include("catalog.urls", namespace="catalog")),
    path("orders/", include("orders.urls", namespace="orders")),
    path("comments/", include("interactions.urls", namespace="interactions")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

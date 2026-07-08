"""users 应用 API 路由。"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from users.views import (
    CurrentUserApiView,
    PublicUserApiView,
    RegisterApiView,
    TokenPairApiView,
    UserAddressDetailApiView,
    UserAddressListCreateApiView,
    UserAddressSetDefaultApiView,
)

urlpatterns = [
    path("auth/register/", RegisterApiView.as_view(), name="auth_register"),
    path("auth/token/", TokenPairApiView.as_view(), name="auth_token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="auth_token_refresh"),
    path("users/me/", CurrentUserApiView.as_view(), name="users_me"),
    path(
        "users/me/addresses/",
        UserAddressListCreateApiView.as_view(),
        name="users_me_addresses",
    ),
    path(
        "users/me/addresses/<int:pk>/",
        UserAddressDetailApiView.as_view(),
        name="users_me_address_detail",
    ),
    path(
        "users/me/addresses/<int:pk>/set-default/",
        UserAddressSetDefaultApiView.as_view(),
        name="users_me_address_set_default",
    ),
    path("users/<int:user_id>/", PublicUserApiView.as_view(), name="users_public"),
]


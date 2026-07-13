"""users 应用 API 路由。"""

from django.urls import path

from users.views import (
    CurrentUserAPIView,
    PublicUserAPIView,
    RegisterAPIView,
    ThrottledTokenRefreshView,
    TokenPairAPIView,
    UserAddressDetailAPIView,
    UserAddressListCreateAPIView,
    UserAddressSetDefaultAPIView,
)

urlpatterns = [
    path("auth/register/", RegisterAPIView.as_view(), name="auth_register"),
    path("auth/token/", TokenPairAPIView.as_view(), name="auth_token"),
    path(
        "auth/token/refresh/",
        ThrottledTokenRefreshView.as_view(),
        name="auth_token_refresh",
    ),
    path("users/me/", CurrentUserAPIView.as_view(), name="users_me"),
    path(
        "users/me/addresses/",
        UserAddressListCreateAPIView.as_view(),
        name="users_me_addresses",
    ),
    path(
        "users/me/addresses/<int:pk>/",
        UserAddressDetailAPIView.as_view(),
        name="users_me_address_detail",
    ),
    path(
        "users/me/addresses/<int:pk>/set-default/",
        UserAddressSetDefaultAPIView.as_view(),
        name="users_me_address_set_default",
    ),
    path("users/<int:user_id>/", PublicUserAPIView.as_view(), name="users_public"),
]


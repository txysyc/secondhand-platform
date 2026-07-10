"""用户与认证 API 类视图。"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from users.serializers import (
    CurrentUserSerializer,
    ProfileSerializer,
    PublicUserSerializer,
    TokenPairSerializer,
    UserAddressSerializer,
    UserRegisterSerializer,
)
from users.models import Profile, User, UserAddress


class RegisterApiView(APIView):
    """注册用户。"""

    permission_classes = [AllowAny]
    throttle_scope = "auth_register"

    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            CurrentUserSerializer(user, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TokenPairApiView(APIView):
    """使用用户名或邮箱获取 JWT token。"""

    permission_classes = [AllowAny]
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = TokenPairSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class ThrottledTokenRefreshView(TokenRefreshView):
    """带限流保护的 JWT refresh token 接口。"""

    throttle_scope = "auth_refresh"


class CurrentUserApiView(APIView):
    """当前用户资料读取与更新。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        Profile.objects.get_or_create(user=request.user)
        serializer = CurrentUserSerializer(
            request.user,
            context={"request": request},
        )
        return Response(serializer.data)

    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        serializer = ProfileSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        response_serializer = CurrentUserSerializer(
            request.user,
            context={"request": request},
        )
        return Response(response_serializer.data)


class PublicUserApiView(APIView):
    """公开用户主页。"""

    permission_classes = [AllowAny]

    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        Profile.objects.get_or_create(user=user)
        serializer = PublicUserSerializer(user, context={"request": request})
        return Response(serializer.data)


class UserAddressListCreateApiView(APIView):
    """当前用户收货地址列表与新增。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        addresses = UserAddress.objects.filter(user=request.user).order_by(
            "-is_default", "-updated_at", "-id"
        )
        serializer = UserAddressSerializer(addresses, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = UserAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            has_address = UserAddress.objects.select_for_update().filter(
                user=request.user
            ).exists()
            should_set_default = serializer.validated_data.get(
                "is_default", not has_address
            )
            if should_set_default:
                UserAddress.objects.filter(user=request.user, is_default=True).update(
                    is_default=False
                )
            address = serializer.save(user=request.user, is_default=should_set_default)

        return Response(
            UserAddressSerializer(address).data,
            status=status.HTTP_201_CREATED,
        )


class UserAddressDetailApiView(APIView):
    """当前用户单个收货地址读取、修改与删除。"""

    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        return get_object_or_404(UserAddress, pk=pk, user=request.user)

    def get(self, request, pk):
        address = self.get_object(request, pk)
        return Response(UserAddressSerializer(address).data)

    def patch(self, request, pk):
        address = self.get_object(request, pk)
        serializer = UserAddressSerializer(address, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            address = UserAddress.objects.select_for_update().get(
                pk=address.pk,
                user=request.user,
            )
            should_set_default = serializer.validated_data.get("is_default")
            if should_set_default is True:
                UserAddress.objects.filter(user=request.user, is_default=True).exclude(
                    pk=address.pk
                ).update(is_default=False)
            address = serializer.save()

        return Response(UserAddressSerializer(address).data)

    def delete(self, request, pk):
        address = self.get_object(request, pk)
        address.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserAddressSetDefaultApiView(APIView):
    """将当前用户的某个收货地址设为默认地址。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        with transaction.atomic():
            address = get_object_or_404(
                UserAddress.objects.select_for_update(),
                pk=pk,
                user=request.user,
            )
            UserAddress.objects.filter(user=request.user, is_default=True).exclude(
                pk=address.pk
            ).update(is_default=False)
            address.is_default = True
            address.save(update_fields=["is_default", "updated_at"])

        return Response(UserAddressSerializer(address).data)


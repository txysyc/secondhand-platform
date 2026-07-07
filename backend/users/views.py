"""用户与认证 API 类视图。"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.serializers import (
    CurrentUserSerializer,
    ProfileSerializer,
    PublicUserSerializer,
    TokenPairSerializer,
    UserRegisterSerializer,
)
from users.models import Profile, User


class RegisterApiView(APIView):
    """注册用户。"""

    permission_classes = [AllowAny]

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

    def post(self, request):
        serializer = TokenPairSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


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


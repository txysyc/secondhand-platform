"""项目级 API 基础类视图。"""

from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status


class APIRootView(APIView):
    """返回 API 基础信息，作为 `/api/v1/` 的稳定入口。"""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "name": "secondhand-platform API",
                "version": "v1",
                "status": "ok",
            },
        )


class AuthenticatedProbeView(APIView):
    """验证 JWT 认证配置是否生效的项目级探针。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "authenticated": True,
            },
        )


class StaffProbeView(APIView):
    """验证 DRF 权限失败响应是否保持 JSON 结构。"""

    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(
            {"staff": True},
        )

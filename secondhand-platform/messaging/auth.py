"""私信 WebSocket JWT 鉴权中间件。"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class JwtAuthMiddleware:
    """从 WebSocket query string 中读取 access token 并写入 scope user。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = self._get_token(scope)
        scope = dict(scope)
        scope["user"] = await self._authenticate(token)
        return await self.app(scope, receive, send)

    def _get_token(self, scope):
        """从 query string 中提取前端传入的 access token。"""

        query_string = scope.get("query_string", b"").decode()
        values = parse_qs(query_string).get("token", [])
        return values[0] if values else None

    @database_sync_to_async
    def _authenticate(self, token):
        """在线程池中复用 SimpleJWT 的同步认证逻辑。"""

        if not token:
            return AnonymousUser()
        authenticator = JWTAuthentication()
        try:
            validated_token = authenticator.get_validated_token(token)
            return authenticator.get_user(validated_token)
        except (InvalidToken, TokenError):
            return AnonymousUser()


def JwtAuthMiddlewareStack(inner):
    """构造 Channels 使用的 JWT 鉴权中间件栈。"""

    return JwtAuthMiddleware(inner)

"""DRF 限流复用组件。"""

from rest_framework.throttling import SimpleRateThrottle


class MethodScopedThrottleMixin:
    """按 HTTP 方法选择限流 scope，避免读接口被写接口限流误伤。"""

    method_throttle_scopes = {}

    def get_throttles(self):
        """在实例化限流类前为当前请求方法设置 throttle_scope。"""

        scope = self.method_throttle_scopes.get(self.request.method)
        if scope is None:
            self.throttle_scope = None
        else:
            self.throttle_scope = scope
        return super().get_throttles()


class UserScopedSimpleRateThrottle(SimpleRateThrottle):
    """供 WebSocket 等非 DRF 视图按用户或 IP 复用的简单限流器。"""

    scope = None

    def __init__(self, scope):
        self.scope = scope
        super().__init__()

    def get_cache_key(self, request, view):
        """优先按登录用户限流，匿名请求退回到 IP 限流。"""

        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            ident = f"user:{user.pk}"
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

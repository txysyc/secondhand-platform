"""项目级 API 视图复用组件。"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response


class ServiceErrorMixin:
    """将服务层 Django 异常转换为统一的 DRF JSON 错误响应。"""

    def run_service(self, func, *args, **kwargs):
        """执行服务函数，并把业务异常映射为 API 可识别的异常类型。"""

        try:
            return func(*args, **kwargs)
        except DjangoValidationError as exc:
            # 服务层使用 Django ValidationError 表达业务规则失败；
            # 这里统一转成 DRF ValidationError，交给全局异常处理器包装。
            message = exc.messages[0] if getattr(exc, "messages", None) else "请求处理失败"
            raise ValidationError(detail=message)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(detail=str(exc))


class PageNumberPaginationMixin:
    """为不需要完整 DRF 分页类的轻量列表 API 提供统一分页响应。"""

    page_size = 20
    serializer_class = None

    def paginate(self, request, queryset, serializer_class=None):
        """按 page 查询参数分页，并返回 count/next/previous/results 结构。"""

        serializer_class = serializer_class or self.serializer_class
        if serializer_class is None:
            raise AssertionError("必须提供 serializer_class 或定义 self.serializer_class")

        page_number = self._parse_page_number(request)
        total = queryset.count()
        start = (page_number - 1) * self.page_size
        end = start + self.page_size
        items = list(queryset[start:end])
        next_page = page_number + 1 if end < total else None
        previous_page = page_number - 1 if page_number > 1 else None

        return Response(
            {
                "count": total,
                "next": None if next_page is None else self._page_url(request, next_page),
                "previous": (
                    None
                    if previous_page is None
                    else self._page_url(request, previous_page)
                ),
                "results": serializer_class(
                    items,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )

    def _parse_page_number(self, request):
        """把非法 page 参数降级为第一页，避免列表接口因页码格式直接失败。"""

        page_number = request.query_params.get("page", 1)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1
        return max(page_number, 1)

    def _page_url(self, request, page_number):
        """基于当前请求构造保留筛选参数的分页链接。"""

        query_params = request.query_params.copy()
        query_params["page"] = page_number
        return f"{request.build_absolute_uri(request.path)}?{query_params.urlencode()}"

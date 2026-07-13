"""项目级 API 视图复用组件。"""

import math

from rest_framework.response import Response


class PageNumberPaginationMixin:
    """为不需要完整 DRF 分页类的轻量列表 API 提供统一分页响应。"""

    page_size = 20
    max_page_size = 100
    serializer_class = None

    def paginate(self, request, queryset, serializer_class=None):
        """按 page 查询参数分页，并返回 count/next/previous/results 结构。"""

        serializer_class = serializer_class or self.serializer_class
        if serializer_class is None:
            raise AssertionError(
                "必须提供 serializer_class 或定义 self.serializer_class"
            )

        total = queryset.count()
        page_size = self._parse_page_size(request)
        max_page_number = math.ceil(total / page_size)
        page_number = self._parse_page_number(request, max_page_number)
        start = (page_number - 1) * page_size
        end = start + page_size
        items = list(queryset[start:end])
        next_page = page_number + 1 if end < total else None
        previous_page = page_number - 1 if page_number > 1 else None

        return Response(
            {
                "count": total,
                "next": None
                if next_page is None
                else self._page_url(request, next_page),
                "previous": (
                    None
                    if previous_page is None
                    else self._page_url(request, previous_page)
                ),
                "page_size": page_size,
                "results": serializer_class(
                    items,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )

    def _parse_page_number(self, request, max_page_number):
        """把非法 page 参数降级为第一页，将超过最大页码变为最大页码，避免列表接口因页码格式直接失败。"""

        page_number = request.query_params.get("page", 1)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1
        # 判断是否会大于最大页码
        if page_number > max_page_number:
            page_number = max_page_number
        # 避免用户传递负页码
        page_number = max(page_number, 1)

        return page_number

    def _parse_page_size(self, request):
        """读取可选 page_size 参数，并限制在安全范围内。"""

        page_size = request.query_params.get("page_size", self.page_size)
        try:
            page_size = int(page_size)
        except (TypeError, ValueError):
            page_size = self.page_size
        return min(max(page_size, 1), self.max_page_size)

    def _page_url(self, request, page_number):
        """基于当前请求构造保留筛选参数的分页链接。"""

        query_params = request.query_params.copy()
        query_params["page"] = page_number
        return f"{request.build_absolute_uri(request.path)}?{query_params.urlencode()}"

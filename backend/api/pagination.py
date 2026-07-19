"""项目级 DRF 分页实现。"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.pagination import replace_query_param
from rest_framework.response import Response


class StandardPageNumberPagination(PageNumberPagination):
    """兼容现有 API 分页协议的 DRF 分页类。

    新的 generic view 使用该类；旧的 ``PageNumberPaginationMixin`` 暂不迁移，
    以便后续按业务模块逐步切换。
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50

    def get_page_number(self, request, paginator):
        """将非法页码归一到首页，超范围页码定位到最后一页。"""

        raw_page = request.query_params.get(self.page_query_param, 1)
        if raw_page in self.last_page_strings:
            return paginator.num_pages
        try:
            page_number = int(raw_page)
        except (TypeError, ValueError):
            return 1
        return min(max(page_number, 1), paginator.num_pages)

    def get_paginated_response(self, data):
        """保留项目现有响应中的 page_size 字段。"""

        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page_size": self.get_page_size(self.request),
                "results": data,
            }
        )

    def get_previous_link(self):
        """保留旧分页协议中的显式 ``page=1``。"""

        if not self.page.has_previous():
            return None
        return replace_query_param(
            self.request.build_absolute_uri(),
            self.page_query_param,
            self.page.previous_page_number(),
        )

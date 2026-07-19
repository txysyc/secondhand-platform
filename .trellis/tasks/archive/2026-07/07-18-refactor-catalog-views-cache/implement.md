# 实施计划

1. 读取 `trellis-before-dev` 指南，确认 backend 视图、缓存和测试约定。
2. 重构 `catalog/cache.py`：整理常量、key builder、safe Redis 操作和 cache-aside 流程，保持公开函数与失效入口兼容；补充架构图。
3. 新增项目级 `api.pagination.StandardPageNumberPagination`，配置为 DRF 全局默认，兼容 `page_size`、最大页大小、页码钳制和响应字段；保留旧 `PageNumberPaginationMixin` 调用方不变。
4. 重构 `catalog/views.py`：优先使用 `ListAPIView`、`CreateAPIView`、`RetrieveUpdateDestroyAPIView` 等具体通用视图，抽取 serializer/context/响应和所有权对象复用，保持 service 调用及分页协议。
5. 视需要调整 `selectors.py`、测试或文档，移除不必要的私有缓存依赖。
6. 执行 `uv run python backend/manage.py check`、`uv run pytest -q --reuse-db backend/catalog`，再运行与全局 API 相关的检查。
7. 运行 Trellis quality check，复核 git diff 只包含本任务范围。

风险回滚点：先完成 cache 单元行为，再改 views；任何 API 回归可通过恢复对应视图类实现回滚，缓存旧 key 允许自然过期。

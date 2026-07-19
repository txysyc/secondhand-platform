# 实施计划

1. 读取 `trellis-before-dev` 及 backend 相关规范，复核 DRF 3.17.1 的 `SearchFilter`、`OrderingFilter` 和 django-filter 调用契约。
2. 在 `catalog/filters.py` 新增继承 DRF 标准类的搜索、排序 backend；复用搜索长度常量并实现字段级中文错误、完整关键词语义、排序别名和默认回退。
3. 从 `ListingFilterSet`、`MyListingFilterSet` 及其表单移除 `q` 搜索职责，保留所有结构化字段与跨字段校验。
4. 调整 `catalog/views.py`：两个列表视图显式声明 `filter_backends`、`filterset_class`、`search_fields`、排序映射和默认排序；`get_queryset()` 仅构建基础 QuerySet 与收藏状态注解。
5. 删除 `catalog/selectors.py` 中不再使用的两个排序 helper，并清理生产代码与测试导入。
6. 删除 `config/settings/base.py` 中的 `DEFAULT_FILTER_BACKENDS`，再次全仓库搜索隐式消费者。
7. 更新 FilterSet、backend/selector 与 API 测试，覆盖结构化筛选、公开/所有者搜索、完整关键词、空白/超长关键词、排序白名单隔离、未知值回退及 `id` 稳定排序。
8. 运行 `uv run python backend/manage.py check`、`uv run pytest -q --reuse-db backend/catalog`；再运行受 DRF settings 影响的 interactions/orders API 测试。
9. 使用 `trellis-check` 完成最终质量检查，列出 diff、测试结果、风险和未纳入路径，等待用户人工审查与明确提交确认。

## 风险文件与回滚点

- `backend/catalog/filters.py`：搜索错误结构和 DRF 搜索语义。
- `backend/catalog/views.py`：backend 执行顺序及两个列表视图配置。
- `backend/catalog/selectors.py`：删除旧排序规则前必须确保新 backend 测试覆盖完全。
- `backend/config/settings/base.py`：删除全局配置后必须用全仓库搜索与相关 API 测试确认无隐式消费者。

本任务不修改 `backend/api/pagination.py`、缓存、模型、迁移、URL 或前端代码；出现契约回归时整体恢复上述四个生产文件即可。

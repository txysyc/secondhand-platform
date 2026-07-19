# PRD：标准化 catalog 过滤与排序后端

## 目标

在不改变商品列表 API 查询参数、响应结构和错误契约的前提下，让公开商品列表与“我的商品”列表使用 DRF 标准过滤流程，移除视图中手工实例化 FilterSet 和调用 selector 排序函数的编排逻辑。

## 背景与已确认事实

- `ListingListAPIView` 与 `MyListingListCreateAPIView` 已是 DRF generic views，但 `get_queryset()` 仍通过 `_filter_listing_queryset()` 手工执行收藏状态注解、FilterSet 校验和排序。
- `REST_FRAMEWORK.DEFAULT_FILTER_BACKENDS` 当前只包含 `DjangoFilterBackend`；全仓库没有其他视图声明 `filterset_class` 或依赖该全局设置。
- 公开列表与所有者列表分别使用 `ListingFilterSet`、`MyListingFilterSet`，两者都重复实现了 `q` 的去空白、最长 50 字符校验及标题/描述搜索。
- `catalog.selectors` 中的 `apply_public_listing_sort()` 与 `apply_owner_listing_sort()` 只负责列表排序白名单；视图是生产代码中的唯一调用方，其他引用均为测试。
- 项目已全局使用 `api.pagination.StandardPageNumberPagination`。本任务不调整分页机制。
- 现有异常处理器要求所有可预期 API 错误保持 `message + errors` 结构，并优先展示中文字段错误。

## 需求

1. 删除 DRF settings 中的全局 `DEFAULT_FILTER_BACKENDS`，需要过滤的视图通过 `filter_backends` 显式声明自身依赖。
2. 两个商品列表视图使用 `DjangoFilterBackend` 和各自的 `filterset_class` 处理结构化筛选，不再手工创建 FilterSet 或抛出其校验错误。
3. 基于 DRF `SearchFilter` 实现 catalog 搜索 backend，查询参数保持为 `q`；搜索词去除首尾空白，空白搜索不限制结果，超过 50 字符返回中文 400 错误，搜索范围保持标题或描述。
4. 基于 DRF `OrderingFilter` 实现 catalog 排序 backend，查询参数保持为 `sort`，并把外部排序别名映射为受控 ORM 排序字段。
5. 公开列表继续支持 `oldest`、`price_asc`、`price_desc`，默认按 `-published_at, -id` 排序；所有者列表继续支持 `updated_asc`、`published_desc`、`published_asc`、`price_asc`、`price_desc`，默认按 `-updated_at, -id` 排序。
6. 所有排序都必须包含 `id` 次级排序，保证分页结果稳定；未知或空排序值保持现有行为，回退到对应列表的默认排序。
7. 收藏状态注解继续在基础 queryset 构建阶段完成，再由 DRF 依次执行结构化筛选、搜索、排序和分页。
8. 删除被新 backends 取代的视图 helper、FilterSet 搜索字段/校验和 selector 排序 helper，避免保留两套规则来源。

## 验收标准

- [ ] `ListingListAPIView` 和 `MyListingListCreateAPIView` 显式配置三个过滤 backend，并分别声明正确的 `filterset_class`。
- [ ] `views.py` 中不再存在 `_filter_listing_queryset()` 或手工 `FilterSet.is_valid()` 调用。
- [ ] 公开列表和所有者列表的结构化筛选、`q` 搜索、`sort` 排序、默认排序及分页响应与重构前兼容。
- [ ] 搜索词首尾空白、纯空白、超过 50 字符以及标题/描述 OR 搜索均有回归测试；超长搜索保持中文 `message/errors` 400 响应。
- [ ] 两类列表各自只接受自身排序别名，未知值回退默认排序，等值字段按 `id` 稳定排序。
- [ ] 删除全局过滤后端后，catalog 以外现有 API 行为不因隐式过滤配置发生变化。
- [ ] `uv run python backend/manage.py check` 与 `uv run pytest -q --reuse-db backend/catalog` 通过；根据配置影响补充相关 API 测试。
- [ ] 不修改 URL、serializer 字段、权限、分页类、缓存机制、数据库模型或前端接口。

## 非目标

- 不迁移其他 app 的过滤、搜索或排序实现。
- 不新增查询参数，不改用 DRF 默认的 `search` 或 `ordering` 参数名。
- 不改变当前多关键词语义；去空白后的 `q` 仍作为一个完整关键词匹配标题或描述。
- 不调整 `StandardPageNumberPagination`、catalog 缓存或商品可见性规则。

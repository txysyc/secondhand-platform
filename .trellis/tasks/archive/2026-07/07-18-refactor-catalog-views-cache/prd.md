# PRD：重构 catalog 视图与缓存

## 目标

在不改变现有 `/api/v1/catalog/` URL、权限、状态流转、分页和错误响应契约的前提下，降低 `backend/catalog/views.py` 与 `backend/catalog/cache.py` 的认知复杂度，提升后续维护和复用效率。

## 背景与已确认事实

- `backend/catalog/views.py` 的所有 endpoint 当前直接或间接继承 `APIView`，列表、详情、创建、更新、删除和动作接口重复编排 serializer、对象查询和响应构造。
- `PageNumberPaginationMixin` 已被多个旧 API 使用，`selectors.py` 与 `services.py` 已承载大部分查询和业务动作；DRF settings 已配置默认分页类但当前 catalog 仍手工调用 mixin。
- 公开列表、当前用户列表、公开详情和所有权校验详情有不同 queryset/权限边界，不能简单合并为一个 queryset。
- `backend/catalog/cache.py` 同时实现版本化 key、缓存互斥锁、Redis 异常降级、空值短 TTL、随机 TTL 抖动和分类 ID 摘要校验；`selectors.py` 当前直接导入 `_active_category_ids_cache_key`。
- 现有 `backend/catalog/tests/test_07_api.py` 和 `test_08_cache.py` 覆盖主要 API 行为、缓存命中、缓存失效和不存在对象的空值缓存。
- 工作区已有用户改动：`backend/catalog/cache.py`、`backend/config/settings/base.py` 及一个 `.omo` 运行文件；本任务只处理 catalog 重构相关文件，不回退其他改动。

## 需求

1. 视图优先直接使用 DRF 具体通用类：列表使用 `ListAPIView`，创建使用 `CreateAPIView`，所有者详情使用 `RetrieveUpdateDestroyAPIView`（如 GET/PATCH/DELETE 路由一致），动作接口使用 `GenericAPIView` 保留清晰的专用 action view；只有匿名缓存详情等无法由标准 mixin 表达的部分保留小范围覆写。
2. 将重复的 serializer、分页、过滤、对象获取和响应构造逻辑收敛到类属性、共享基类或项目已有 mixin；权限和 service 边界保持在现有位置。
3. 公开匿名详情继续支持缓存；登录用户详情继续执行可见性校验、收藏状态注解和浏览记录逻辑。
4. 缓存 API 采用按“分类缓存、公开详情缓存、Redis 安全封装”分层的易读结构；保留 Redis 不可用时的数据库降级，避免缓存故障影响请求。
5. 缓存失效必须继续覆盖分类变更、公开可见性变更、商品及商品图片变更；不存在的公开详情继续使用短 TTL 防止重复回源。
6. 在 `cache.py` 顶部加入简要 ASCII 架构图；如新增整体文档，按模块预留 catalog 缓存章节，便于后续扩展。
7. 补充或调整测试，证明重构前后 API 响应和缓存行为一致，并覆盖新增的通用视图/缓存边界。

## 验收标准

- 现有 catalog API 测试通过，URL、状态码、响应字段、权限和分页结构无回归。
- `views.py` 不再让所有 endpoint 直接依赖 `APIView`；重复逻辑明显减少，读写职责通过 DRF generic view/mixin 表达。
- `cache.py` 的公开函数职责清晰，调用方不需要理解版本 key 的拼接细节；缓存命中、并发回源、空值缓存和 Redis 故障降级均有测试或现有测试保护。
- `selectors.py` 不再依赖不必要的缓存内部实现；若保留兼容导出，需有明确注释和测试理由。
- `uv run python backend/manage.py check`、catalog 测试及相关静态检查通过。
- 不引入数据库迁移，不改变缓存后端配置，不改变前端接口契约。
- 列表分页继续返回 `count/next/previous/page_size/results`，`page_size` 查询参数最大值保持 catalog 现有的 50，非法/越界页码行为保持兼容。

## 非目标

- 不重设计订单、互动或其他 app 的缓存。
- 不新增 API endpoint，不调整前端页面，不更改业务状态机和权限规则。
- 不立即迁移其他 app 当前使用的 `PageNumberPaginationMixin`；新增项目级 DRF 分页类并配置为全局默认，旧视图继续兼容，后续按模块逐步迁移。

## 方案评估与决策

- 视图：接受直接使用 `ListAPIView`、`CreateAPIView`、`RetrieveUpdateDestroyAPIView` 等具体类；这比显式组合 mixin 更符合当前 endpoint 语义，也能减少自定义 `get/post/patch/delete` 样板代码。
- 分页：新增项目级 `api.pagination.StandardPageNumberPagination`，使用 DRF `PageNumberPagination` 作为基类。它原生支持 `page`，通过配置 `page_size_query_param` 支持 `page_size`；只重写 `get_page_number()` 以保留非法/负数回首页和超范围定位最后一页，并重写 `get_paginated_response()` 补充现有 `page_size` 字段。将其设为 `REST_FRAMEWORK.DEFAULT_PAGINATION_CLASS`，catalog 新 generic views 直接复用；旧 `PageNumberPaginationMixin` 调用方保持不变。
- 缓存：版本化 key + 失效信号 + Redis 故障降级的核心机制合理，适合继续使用；分类 ID digest 只用于修复局部缓存损坏，属于额外防护而非主流程。重构会把版本 key、锁和 safe Redis 操作隐藏在 cache facade 内，优先移除重复读取和调用方对私有 key builder 的依赖，不做无依据的全量机制替换。
- 外部契约和缓存后端保持兼容；若需要改变 URL/响应格式或进行缓存 key 全量迁移，应另开任务。

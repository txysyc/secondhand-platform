# 技术设计

## 视图边界

- `CategoryListAPIView` 使用 `GenericAPIView`（该接口返回缓存 payload 而不是模型 serializer 列表）。
- 公开列表使用 `ListAPIView`，在 `get_queryset()` 中完成 selector、收藏注解、FilterSet 校验和白名单排序；serializer 与 paginator 通过类属性声明。
- “我的商品列表/创建”拆为两个 DRF 视图类并在 URL 层绑定同一路径的不同 method view，或使用保留 method dispatch 的轻量组合；优先选择不重复业务逻辑且不改变现有 URL 的实现。
- 公开详情使用 `RetrieveAPIView` 的对象读取能力，但匿名缓存与登录后浏览记录需要在 `get()` 中保留；抽出 `get_queryset()`、`get_serializer_context()` 和 payload builder。
- 所有者详情使用 `RetrieveUpdateDestroyAPIView`，通过 `get_serializer_class()` 区分读写 serializer，`perform_update/perform_destroy` 调用现有 services，所有权检查集中在基类。
- 发布、下架、重新上架、图片上传/删除/重排继续使用专用 `GenericAPIView` action views，共享所有权对象基类和详情响应 helper。

## 分页设计

新增项目级 `backend/api/pagination.py` 中的 `StandardPageNumberPagination`。DRF 原生处理 `page`，通过 `page_size_query_param = "page_size"` 开启客户端页大小并以 `max_page_size = 50` 限制上限；重写 `get_page_number()` 将非法/负数页码归一到首页、将超范围页码归一到最后一页，重写 `get_paginated_response()` 补充现有 `page_size` 字段。空列表沿用 DRF 的稳定空结果，并在 `REST_FRAMEWORK.DEFAULT_PAGINATION_CLASS` 中设为全局默认。

catalog 新的 `ListAPIView` 直接使用全局类，不再有商品专用 paginator。当前仍继承 `PageNumberPaginationMixin` 的 interactions/orders 等旧视图不改动；它们的分页逻辑和新类并存，后续模块迁移时再统一。

## 缓存分层

1. 公开 facade：`get_active_category_ids()`、`get_active_category_payload()`、`get_cached_public_listing_detail()`。
2. 领域 key/失效：分类版本、公开详情全局版本、单商品版本，以及对应失效函数。
3. Redis 安全访问：统一处理 get/add/set 异常、缓存未命中哨兵、互斥锁和回源降级。

版本化 key 机制继续保留以避免批量删除；通过命名的小型 helper 明确“读取、构建、回填、降级”流程。分类 ID 摘要暂时保留，因为已有测试覆盖局部缓存不一致时刷新；重构其调用路径但不改变该防护语义。

## 兼容性与风险

- 外部 URL、权限、状态码和 serializer 字段不变。
- 缓存 key 可能因内部简化而变化；部署时允许一次自然冷缓存，不要求迁移旧 key。
- Redis 异常路径必须返回数据库结果；锁竞争不等待，避免请求延迟放大。
- 先保留现有失效函数名，减少 signals/management command 的改动；必要时新增公开 helper，逐步移除调用方对私有 key helper 的依赖。

## 文档

在 `cache.py` 模块 docstring 中放置 catalog 缓存 ASCII 图，标出请求、版本化 key、Redis、数据库回源和 signals 失效路径；若已有 docs 缓存总览则追加 catalog 小节，否则不扩大文档范围。

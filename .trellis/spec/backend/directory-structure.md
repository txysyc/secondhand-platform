# 后端目录与模块结构

## 项目边界

后端代码位于 `backend/`，运行时是 Django 6、Django REST Framework、Channels 和 Celery。项目采用按业务域拆分的 Django app，而不是把所有视图、服务集中到一个目录。

```text
backend/
├── config/                 # Django 设置、根路由、ASGI、Celery
├── api/                    # 跨业务 API 入口、异常、分页、限流
├── users/                  # 用户、资料、地址与认证
├── catalog/                # 分类、商品、图片、筛选和缓存
├── orders/                 # 订单模型、状态机、履约服务和异步任务
├── interactions/           # 评论、收藏、浏览历史
├── messaging/              # 私信 HTTP API、WebSocket 和缓存
├── notifications/          # 通知模型、查询和实时推送
└── conftest.py             # pytest 共享夹具
```

前端位于 `frontend/`，通过 `frontend/src/api/endpoints/` 调用 `/api/v1/` 下的接口；不要把前端代码或模板复制到 `backend/` app 中。

## 单个业务 app 的文件职责

- `models.py`：持久化模型、枚举、数据库约束和模型级校验。示例：`catalog/models.py` 的 `Listing` 状态枚举和索引。
- `serializers.py`：DRF 输入/输出契约和请求参数校验。示例：`catalog/serializers.py` 的 `ListingWriteSerializer` 合并 PATCH 原值后校验实体/虚拟商品字段。
- `selectors.py`：只读 QuerySet 构造、可见性、排序和预取。示例：`catalog/selectors.py` 的 `get_visible_listing_detail_queryset`。
- `services.py`：跨模型业务动作、权限检查、事务和状态流转。示例：`orders/services.py` 的支付、发货、收货流程。
- `views.py`：路由边界、认证/限流声明、调用 serializer/selector/service，并返回 `Response`；不要在视图里重新实现状态机。
- `urls.py`：只声明 `path()`，由 `api/urls.py` 聚合到 `/api/v1/`。
- `permissions.py`、`filters.py`：可复用的对象权限和查询过滤器。
- `cache.py`：缓存键、读取、失效和 Redis 降级逻辑；业务写入通过 signals 或 service 触发失效。
- `tasks.py`：Celery 任务薄包装，实际业务仍调用 `services.py`。
- `consumers.py`、`routing.py`：异步 WebSocket 入口和路由；数据库访问通过 `database_sync_to_async` 调用同步 service/selector。
- `tests/`：按模型、管理后台、selector、service、API、缓存/消费者等责任编号（如 `test_01_models.py`、`test_07_api.py`）。

## 命名与新增模块

- 模块文件使用小写下划线；公开类使用 PascalCase，函数和变量使用 snake_case。
- 新增业务功能优先放入已有 app；只有存在独立模型、URL 前缀和生命周期时才创建新 app。
- 共享 API 行为放在 `api/`（例如 `PageNumberPaginationMixin`、`api_exception_handler`），不要在每个 app 复制。
- 每个新模块应添加中文 docstring 或注释说明非显然的业务规则，保持现有 Django 风格。

## 常见反模式

- 在 `views.py` 直接修改多个模型、发送通知或处理文件删除，导致无法复用和无法保证事务。
- 在 `selectors.py` 写入数据库，或在 `services.py` 为列表接口拼接未经白名单检查的排序字段。
- 让 WebSocket consumer 直接执行同步 ORM；必须通过 `database_sync_to_async`。
- 在根目录新增与业务 app 平行的散落工具文件；跨域工具应放入 `api/` 或明确归属的 app。

参考：`backend/api/urls.py`、`backend/catalog/views.py`、`backend/orders/services.py`、`backend/messaging/consumers.py`。

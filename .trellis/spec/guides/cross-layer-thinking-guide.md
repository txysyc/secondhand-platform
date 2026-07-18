# 跨层数据流思维指南

## 项目中的边界

典型链路是：

```text
React 页面 → frontend/src/api/endpoints → apiClient → /api/v1/
→ DRF view → serializer/selector/service → PostgreSQL/Redis/Celery
```

实时消息另外经过：

```text
React WebSocket → config/asgi.py → messaging/notifications consumer
→ service → channel layer → JSON 事件
```

实现跨层需求前，先列出每个边界的输入、输出、错误格式、认证方式和时间/金额表示。

## 必须保持的契约

- API 根路径是 `/api/v1/`；根路由由 `backend/api/urls.py` 聚合，前端 endpoint 不应绕过 `apiClient`。
- API 错误统一为 `{message, errors}`；前端 `frontend/src/api/client.ts` 依赖这两个字段处理提示和 token 失效。
- 认证使用 `Authorization: Bearer <access_token>`；刷新失败要清理 localStorage 中的 access/refresh token。
- 列表接口使用 `count/next/previous/page_size/results`；分页参数由 `PageNumberPaginationMixin` 限制范围。
- 日期时间由 Django 使用时区感知值，JSON 序列化为 ISO 字符串；金额保持 Decimal 的两位小数语义。
- 订单保存商品标题、价格、首图和地址快照；不要让删除地址或编辑商品改变历史订单展示。
- WebSocket 错误使用 `type=error`，正常私信使用 `type=message`；认证/权限关闭码为 4401/4403。

## 跨层变更检查

1. 先更新或确认后端模型、serializer、URL、service 和测试，再检查 `frontend/src/types/` 与 endpoint 是否需要同步。
2. 对每个新增字段追踪“写入 → 序列化 → 网络 → 解析 → 展示”的完整往返，覆盖空值、错误和权限分支。
3. 修改订单或商品状态时同时检查 Celery 自动任务、通知、缓存失效和前端可用操作列表。
4. 修改 Redis/Channels 行为时确认开发环境端口和独立 DB（缓存默认 DB 2，Channels 默认 DB 3）以及故障降级策略。
5. 对 WebSocket 和 Celery 的同步 ORM 调用保持异步边界：consumer 使用 `database_sync_to_async`，任务调用 service 而不是复制查询。

## 常见跨层错误

- 后端新增响应字段但未更新前端 TypeScript 类型，页面运行时读取 `undefined`。
- 后端返回 DRF 原始错误结构，前端只读 `message` 导致用户看不到字段错误。
- 只修改手动订单流程，忘记 `orders/tasks.py` 的超时取消、自动签收和自动完成。
- 只清理数据库记录而未使用 `transaction.on_commit` 删除媒体文件，或修改后未失效详情缓存。
- 把前端筛选值直接拼接为 ORM `order_by`，跳过后端白名单和权限可见性。

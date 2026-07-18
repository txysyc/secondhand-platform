# 错误处理规范

## 统一 API 契约

`config/settings/base.py` 将 DRF 异常处理器配置为 `api.exceptions.api_exception_handler`。所有可预期的 API 错误都返回：

```json
{
  "message": "面向用户的首条中文消息",
  "errors": {"field": ["字段错误"]}
}
```

`api_exception_handler` 保留 DRF 原始错误结构到 `errors`，并从 `detail` 或字段错误提取 `message`；429 固定返回“请求过于频繁，请稍后再试”。未知异常返回 HTTP 500 和通用消息，不向客户端暴露堆栈。

## 分层抛出异常

- service 层使用 `rest_framework.exceptions.ValidationError` 表示业务规则、状态冲突和输入不满足条件；使用 `PermissionDenied` 表示已登录但没有对象权限。示例：`orders/services.py` 的订单状态检查。
- serializer 负责字段类型、必填项和跨字段输入校验，并把错误映射到字段名（见 `catalog/serializers.py:ListingWriteSerializer.validate`）。
- selector/view 对不存在的资源返回 404；对象权限失败返回 403，不能把“没有权限”伪装成成功响应。
- 视图通常让 DRF 统一处理异常，不要捕获后重新构造另一套 JSON。只有确需改变状态码的业务异常才定义明确的异常类，例如 `orders/views.py:OrderCreationConflict` 返回 409。

## HTTP 与 WebSocket

- 认证由 JWT `Bearer` 头完成；匿名访问受保护 API 应得到 401，对象权限失败得到 403，测试需断言状态码和 `message/errors`。
- 成功删除返回 204；创建返回 201；重复幂等创建可返回 200（见订单创建视图）。
- WebSocket consumer 不返回 HTTP 异常，使用 `{"type": "error", "message": "..."}` 发送可展示消息；认证失败在连接阶段关闭 4401，权限失败关闭 4403。参考 `messaging/consumers.py`。

## 资源清理与副作用

- 事务内发生异常时让异常继续冒泡，依靠 `atomic()` 回滚，不要手动“补偿”半提交状态。
- 文件删除、通知等副作用注册在 `transaction.on_commit()`，避免数据库回滚后仍删除文件或发送假通知。
- 缓存/Redis 故障应按现有实现降级到数据库并记录 warning（`catalog/cache.py`）；不应因为缓存不可用返回 500。

## 常见错误

- 在 service 层抛出 Django `ValidationError` 后不转换，导致 API 错误结构不稳定；需要像 `catalog/services.py:_full_clean_listing` 一样转换为 DRF `ValidationError`。
- 捕获所有 `Exception` 后返回 400，掩盖真正的服务器错误；仅捕获能明确处理的异常。
- 直接把 `response.data` 当作字符串展示，丢失字段错误；前端 `frontend/src/api/client.ts` 依赖 `message` 与 `errors` 两层结构。

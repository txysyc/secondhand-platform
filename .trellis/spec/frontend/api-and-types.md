# API 与类型契约

## 请求入口

所有 HTTP 请求必须通过 `src/api/client.ts` 导出的 `apiClient`。它负责：

- 使用 `VITE_API_BASE_URL`，默认 `/api/v1`。
- 构造查询参数时跳过 `undefined` 和 `null`，不能把未填写筛选条件发送为字符串 `undefined` 或 `null`。
- 自动附加 `Authorization: Bearer <access_token>`。
- JSON body 自动设置 `Content-Type`，`FormData` 保留浏览器生成的 multipart boundary。
- 401 时用 refresh token 单飞刷新，并让等待中的请求共享新 access token。
- 204 返回 `null`；非 2xx 统一解析为 `{status, message, errors}`。

业务 endpoint 按域放在 `src/api/endpoints/`，例如 `listings.ts`、`orders.ts`、`messages.ts`。页面只调用这些具名函数，不直接调用 `fetch`。

## 类型与序列化

- 后端响应类型放在 `src/types/`，例如 `Listing`、`Order`、`PaginatedResponse<T>`；列表页面依赖 `count/next/previous/page_size/results` 结构。
- 日期时间保持后端 ISO 字符串，在展示层用 `toLocaleString('zh-CN')` 或明确的日期格式化函数转换，不在 API client 中隐式改写。
- 金额按后端字符串 Decimal 保存，展示时再格式化，禁止用浮点数做金额运算。
- FormData 上传使用 endpoint 接收 `FormData`，不要手动设置 `Content-Type`；商品图片上传参考 `uploadListingImage`。
- 订单创建必须携带 `Idempotency-Key`，参考 `src/api/endpoints/orders.ts:createOrder`。

## 错误与认证

后端错误契约是 `{message, errors}`；页面应优先展示 `message`，需要字段提示时读取 `errors`，不要依赖 DRF 内部嵌套结构。登录成功把 access/refresh token 写入 localStorage，刷新失败由 client 的回调清理 token 并由 `AuthProvider` 清空用户。

不要在 endpoint 捕获错误后返回空数组或伪造成功对象；让页面的 loading/error/empty 状态区分网络失败与合法空结果。

## WebSocket 契约

通知连接由 `Layout` 管理，地址使用 `VITE_WS_BASE_URL` 或当前 host，token 通过 query 参数传递；断线重连前清理旧 socket 和 timer。私信页面使用同域消息类型，连接不可用时按 `ChatWindow` 的 HTTP 兜底状态展示。

新增事件字段时同时更新 `types/notifications.ts` 或 `types/messages.ts`、解析代码和展示页面，并覆盖未知/缺失字段的安全分支。

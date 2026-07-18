# 数据库与 ORM 规范

## 技术与迁移

项目使用 Django ORM，开发和生产数据库由 `.env` 中的 `DB_ENGINE/DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT` 配置，当前目标数据库为 PostgreSQL。用户模型固定为 `users.User`（`config/settings/base.py` 的 `AUTH_USER_MODEL`），新增迁移前不要改动该选择。

模型变更后从仓库根目录执行：

```powershell
uv run python backend/manage.py makemigrations
uv run python backend/manage.py migrate
```

迁移文件必须提交到对应 app 的 `migrations/`，不要直接修改已应用的迁移或在运行时代码中创建表。

## 查询分层与性能

- 列表和详情的只读查询放入 `selectors.py`，返回可继续链式过滤的 QuerySet。`catalog/selectors.py` 的公开查询统一 `select_related("category", "owner", "owner__profile")` 并 `prefetch_related("images")`。
- 外键/一对一使用 `select_related`，反向或多值关系使用 `prefetch_related`；序列化器需要的关联必须在 selector 中预取，避免 N+1。
- 排序参数只允许匹配白名单（见 `apply_public_listing_sort`、`apply_order_list_sort`），不得把请求参数直接传给 `order_by()`。
- 大批量状态任务使用 QuerySet `update()`，需要并发保护的订单流程先 `select_for_update()` 再修改。
- 对缓存命中、预取和查询数量有要求时，用 `django_assert_num_queries` 固化行为，参考 `catalog/tests/test_08_cache.py` 与 `orders/tests/test_08_ratings.py`。

## 事务与一致性

- 订单创建、支付、发货、收货、评分和私信写入使用 `transaction.atomic()`；涉及订单与商品的联动必须在同一事务中提交（`orders/services.py`）。
- 竞争资源先锁定再校验，例如支付同时锁定 `Order` 和 `Listing`，防止重复购买。
- 数据库提交后的副作用使用 `transaction.on_commit()`：商品图片物理文件删除见 `catalog/services.py`，卖家通知见 `notifications/services.py` 的 `create_notification_after_commit`。
- 地址、商品标题、首图等订单字段会保存快照，订单详情不要回读会变化的商品资料；参考 `orders/services.py:create_order`。
- 模型 `Meta.indexes`、`UniqueConstraint` 和 `on_delete` 反映业务不变量；例如商品分类使用 `PROTECT`，订单评分通过唯一订单关系防止重复评分。

## 字段和关系命名

- 字段使用 snake_case，时间字段使用 `_at`（`created_at`、`payment_deadline`），布尔字段使用 `is_` 或可读状态名。
- 业务枚举使用模型内 `TextChoices`（如 `Listing.Status`、`Order.OrderStatus`），服务层引用枚举值而不是散落字符串。
- 外键 `related_name` 使用业务复数/语义名，并在 selector 中明确预取路径。
- 金额使用 `DecimalField`，不要用浮点数；当前订单价格和商品价格均保留两位小数。

## 禁止事项与检查

- 不在请求循环中逐条查询关联对象；先检查 selector 和测试的查询数。
- 不使用未经参数化的 raw SQL，也不要通过字符串拼接生成筛选或排序。
- 不在事务提交前删除上传文件、发送通知或依赖外部服务。
- 不绕过 migration 直接改数据库结构；完成后运行 `uv run python backend/manage.py check` 和相关 pytest。

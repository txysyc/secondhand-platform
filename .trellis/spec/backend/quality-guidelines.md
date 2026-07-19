# 后端质量与测试规范

## 工具链

- Python 版本要求 `>=3.13`，依赖和锁文件由 `uv` 管理。
- Django 配置通过 `DJANGO_SETTINGS_MODULE=config.settings.development` 运行 pytest；测试路径为 `backend/`。
- 变更后至少执行 `uv run pytest`；配置、迁移或依赖变化时补充 `uv run python backend/manage.py check`。前后端契约变化时同时执行 `frontend` 的 `npm run lint` 和 `npm run build`。

## 测试组织

每个 app 的 `tests/` 按责任编号，已有顺序是模型、后台、selector、service、API、缓存/消费者等。新行为应放在最接近责任的文件中，并使用中文 docstring 解释关键场景。

- 数据库测试使用 `pytestmark = pytest.mark.django_db`。
- API 测试复用根目录 `backend/conftest.py` 的 `api_client`、`auth_headers` 和 `png_image`，通过 `reverse("api:...")` 获取 URL。
- 需要验证行锁/并发事务的 service 测试使用 `@pytest.mark.django_db(transaction=True)`，参考 `orders/tests/test_04_services_payment.py`。
- 缓存、预取和 N+1 约束用 `django_assert_num_queries` 固化，参考 `catalog/tests/test_08_cache.py`。
- 测试要同时覆盖成功、未认证(401)、无权限(403)、非法输入(400)、不存在(404)和重复/冲突(409 或幂等 200)分支。

## 必须保持的代码模式

- 业务状态流转集中在 service；视图只编排请求和响应。
- 新增可见性或列表查询先扩展 selector，并添加预取/查询数测试。
- 新的 DRF generic list view 使用 `api.pagination.StandardPageNumberPagination`，统一返回 `count/next/previous/page_size/results`；已有 `APIView + PageNumberPaginationMixin` 视图按模块迁移前继续保持原实现。
- 需要筛选、搜索或排序的 generic list view 必须显式声明 `filter_backends` 和 `filterset_class`，不要依赖全局 `DEFAULT_FILTER_BACKENDS`。外部参数名或排序别名与 DRF 默认契约不同时，继承标准 backend 只实现兼容层：

  ```python
  class ListingListAPIView(ListAPIView):
      filter_backends = (DjangoFilterBackend, ListingSearchFilter, ListingOrderingFilter)
      filterset_class = ListingFilterSet
      search_fields = ("title", "description")
      ordering = ("-published_at", "-id")
  ```

  FilterSet 只负责结构化字段和跨字段校验；搜索与排序规则不要再在 `get_queryset()` 中手工执行。排序映射必须使用代码内白名单并包含主键次级排序，禁止把客户端参数直接传给 `order_by()`。测试至少断言有效值、未知值回退、字段级中文错误和等值字段下的稳定顺序。
- 跨模型写入使用 `transaction.atomic()`；订单、库存/商品状态需要 `select_for_update()`。
- 上传文件、缓存和通知等副作用使用已有的 `on_commit` 或失效 helper。
- 新增常量、枚举、错误消息或 API 字段前先 `rg` 搜索所有消费者，避免只改一端。

## 禁止模式

- 复制粘贴现有 service、分页、异常包装或 token 刷新逻辑。
- 在测试中只断言 200 而不验证响应内容、状态迁移或权限边界。
- 为了让测试通过修改生产代码的权限/校验，或用 mock 掩盖真实 ORM 查询。
- 提交 `.env`、媒体文件、构建产物或依赖锁文件之外的临时输出。

## 提交前检查清单

- [ ] 变更涉及的模型、serializer、selector、service、view、URL 和前端 endpoint 已同步。
- [ ] 新增/修改迁移可从空数据库和当前数据库顺利执行。
- [ ] 关键错误响应符合 `message/errors` 契约。
- [ ] 运行 `uv run pytest`、`uv run python backend/manage.py check`，并记录无法运行的外部依赖（PostgreSQL/Redis）。
- [ ] 所有新增代码注释和文档使用中文，且没有模板占位符。

## 测试执行策略

后端测试优先按业务 app 分模块执行；如果某个模块测试数量较大或单次运行无输出，再按测试文件拆分执行。例如：

```powershell
uv run pytest -q backend/config
uv run pytest -q backend/catalog
uv run pytest -q backend/orders/tests/test_03_services_create.py
```

模块或文件测试通过后再视时间运行完整套件。这样可以快速定位阻塞的异步、Redis 或事务测试，避免一次长时间运行掩盖具体失败点。

例如 `backend/interactions` 模块整体可能长时间无输出，但拆成 `test_01_models.py`、`test_02_selectors.py`、`test_03_admin.py`、`test_04_api.py` 和 `test_05_services.py` 后可以分别通过并快速定位问题。

## 测试环境注意

pytest 默认会创建 PostgreSQL 测试库 `test_secondhand_platform`。不要并行启动多个完整 pytest 进程，也不要让上一次进程残留连接；否则会出现测试库已存在但无法删除的 `DuplicateDatabase/ObjectInUse` 错误。确认没有其他会话后可使用 `uv run pytest --reuse-db` 复用测试库；若完整套件长时间无输出，应改为按 app 或测试文件定位，而不是无限等待。

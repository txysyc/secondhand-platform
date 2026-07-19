# 技术设计

## 边界与职责

- selector 只构建可见性、关联预取和默认排序所需的基础 QuerySet，不解析请求参数。
- `DjangoFilterBackend` 调用 `ListingFilterSet` 或 `MyListingFilterSet`，负责分类、状态、类型、价格和时间区间等结构化参数。
- 自定义 `ListingSearchFilter` 继承 DRF `SearchFilter`，负责 `q` 的规范化、长度校验和标题/描述搜索。
- 自定义 `ListingOrderingFilter` 继承 DRF `OrderingFilter`，负责 `sort` 别名白名单、ORM 字段映射、默认回退和稳定次级排序。
- generic view 只声明 backend、FilterSet、搜索字段与排序映射；收藏状态注解保留在 `get_queryset()` 的基础查询阶段。

## 请求数据流

```text
request.query_params
        |
        v
view.get_queryset() -> 可见性 QuerySet -> 收藏状态注解
        |
        v
DjangoFilterBackend -> 结构化筛选与跨字段校验
        |
        v
ListingSearchFilter -> q 去空白/长度校验 -> title OR description
        |
        v
ListingOrderingFilter -> sort 别名映射 -> 稳定 order_by
        |
        v
StandardPageNumberPagination -> serializer -> response
```

## 搜索设计

`ListingSearchFilter.search_param = "q"`。视图通过 `search_fields = ("title", "description")` 声明字段。backend 覆写搜索词解析逻辑，使去空白后的整个值作为单个搜索词交给 DRF 的字段 OR 查询构造；这避免 DRF 默认按空格拆词后改变现有 API 语义。

当 `q` 长度超过 `MAX_LISTING_SEARCH_LENGTH` 时，backend 抛出字段级 DRF `ValidationError`，错误键为 `q`，消息保持“搜索关键词不能超过50个字符”。统一异常处理器继续包装为 `message + errors`。

`q` 将从两个 FilterSet 及其表单 `clean_q()` 中移除，FilterSet 不再承担搜索职责。

## 排序设计

`ListingOrderingFilter.ordering_param = "sort"`。视图声明“外部别名 -> 完整 ORM ordering tuple”的映射和默认 tuple：

| 视图 | sort | ORM ordering |
|---|---|---|
| 公开列表 | 默认/未知 | `-published_at, -id` |
| 公开列表 | `oldest` | `published_at, id` |
| 公开列表 | `price_asc` | `price, id` |
| 公开列表 | `price_desc` | `-price, -id` |
| 所有者列表 | 默认/未知 | `-updated_at, -id` |
| 所有者列表 | `updated_asc` | `updated_at, id` |
| 所有者列表 | `published_desc` | `-published_at, -id` |
| 所有者列表 | `published_asc` | `published_at, id` |
| 所有者列表 | `price_asc` | `price, id` |
| 所有者列表 | `price_desc` | `-price, -id` |

backend 不把客户端值直接传给 `order_by()`。未知值保持原契约并回退默认排序，而不是采用 DRF 默认的静默移除后依赖偶然 queryset 顺序。

原 `apply_public_listing_sort()` 与 `apply_owner_listing_sort()` 删除，相关 selector 测试迁移为 backend 或 API 层行为测试。

## 视图配置

两个列表视图按相同顺序声明：

1. `DjangoFilterBackend`
2. `ListingSearchFilter`
3. `ListingOrderingFilter`

先执行结构化筛选再搜索不会改变结果集合，排序必须最后执行以覆盖基础 QuerySet 默认排序。公开与所有者视图分别声明自己的 `filterset_class` 和排序映射，避免权限域之间共享错误的状态或排序选项。

## 全局配置与兼容性

删除 `DEFAULT_FILTER_BACKENDS` 后，未显式声明 backend 的 generic view 不再隐式运行 django-filter。全仓库搜索确认当前没有其他 `filterset_class` 消费者，因此不会移除既有过滤能力。

URL、权限、serializer、分页、缓存和响应结构均保持不变。变更只涉及请求 QuerySet 的标准化处理，不需要迁移或部署期数据操作。

## 风险与回滚

- 主要风险是 DRF `SearchFilter` 默认分词语义与原完整字符串搜索不同；通过自定义解析和包含空格的测试锁定兼容行为。
- 排序 backend 若漏掉默认排序会导致分页漂移；每个映射都包含 `id`，并增加等价主排序字段测试。
- FilterSet 移除 `q` 后，必须确保两个视图都启用搜索 backend；API 测试同时覆盖公开和所有者列表。
- 回滚可按 `filters.py`、`views.py`、`selectors.py` 和 settings 的单次提交整体恢复，无数据库或缓存状态需要处理。

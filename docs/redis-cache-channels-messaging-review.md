# Redis 缓存与 Channels 私信功能变更审查文档

日期：2026-06-04  
分支：`feature/redis-cache-channels-messaging`

## Redis 容器与连接结论

- Docker 容器：`secondhand-platform-redis`
- 镜像：`redis:latest`
- 状态：`Up 10 minutes`
- 端口映射：`0.0.0.0:6380->6379/tcp`、`[::]:6380->6379/tcp`
- 当前 `.env` 未发现 `DJANGO_CACHE_URL`、`CHANNEL_REDIS_URL`、`CELERY_BROKER_URL`、`CELERY_RESULT_BACKEND` 这四个 Redis 相关覆盖键，因此本地开发会使用代码中的默认 Redis URL。

## Redis 连接配置

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [secondhand-platform/config/settings/base.py](../secondhand-platform/config/settings/base.py#L24) | 24 | 注册 `daphne`，让 ASGI 服务支持 Channels。 |
| [secondhand-platform/config/settings/base.py](../secondhand-platform/config/settings/base.py#L35) | 35 | 注册 `messaging.apps.MessagingConfig`。 |
| [secondhand-platform/config/settings/base.py](../secondhand-platform/config/settings/base.py#L68) | 68 | 设置 `ASGI_APPLICATION = "config.asgi.application"`。 |
| [secondhand-platform/config/settings/base.py](../secondhand-platform/config/settings/base.py#L132) | 132-135 | Django Cache 与 Channels 的默认 Redis 连接改为 `redis://localhost:6380/2` 和 `redis://localhost:6380/3`，对应 `secondhand-platform-redis` 容器的宿主机端口。 |
| [secondhand-platform/config/settings/base.py](../secondhand-platform/config/settings/base.py#L137) | 137-140 | 使用 Django 内置 Redis cache backend。 |
| [secondhand-platform/config/settings/base.py](../secondhand-platform/config/settings/base.py#L144) | 144-148 | 使用 `channels_redis.core.RedisChannelLayer`，WebSocket 群组消息走 Redis。 |
| [secondhand-platform/config/settings/development.py](../secondhand-platform/config/settings/development.py#L25) | 25-27 | Celery broker/result backend 的开发默认连接改为 `redis://localhost:6380/0` 和 `redis://localhost:6380/1`。 |
| [secondhand-platform/config/settings/production.py](../secondhand-platform/config/settings/production.py#L25) | 25-29 | 生产环境继续强制从环境变量读取 Celery、Cache、Channels Redis URL，不使用本地默认端口。 |

## 依赖与 ASGI 入口

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [pyproject.toml](../pyproject.toml#L8) | 8-9 | 新增 `channels[daphne]>=4,<5`、`channels-redis>=4,<5`。 |
| [uv.lock](../uv.lock#L182) | 182-211 | 锁定 `channels` 与 `channels-redis` 依赖。 |
| [uv.lock](../uv.lock#L335) | 335-345 | 锁定 `daphne`。 |
| [uv.lock](../uv.lock#L624) | 624-651 | 锁定 `redis` 包，并把 Channels 依赖写入项目依赖清单。 |
| [secondhand-platform/config/asgi.py](../secondhand-platform/config/asgi.py#L12) | 12-14 | 引入 Channels 的认证、路由和 Host 校验组件。 |
| [secondhand-platform/config/asgi.py](../secondhand-platform/config/asgi.py#L21) | 21 | 引入 `messaging.routing.websocket_urlpatterns`。 |
| [secondhand-platform/config/asgi.py](../secondhand-platform/config/asgi.py#L23) | 23-28 | 使用 `ProtocolTypeRouter` 同时提供 HTTP 与 WebSocket 协议入口。 |
| [secondhand-platform/config/urls.py](../secondhand-platform/config/urls.py#L18) | 18 | 挂载 `/messages/` 到 `messaging.urls`。 |

## 分类 Redis 缓存

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [secondhand-platform/catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L4) | 4 | 引入 `django.core.cache.cache`。 |
| [secondhand-platform/catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L9) | 9-11 | 定义启用分类 ID 的缓存 key 前缀、版本号 key 与 10 分钟超时时间。 |
| [secondhand-platform/catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L49) | 49-59 | `clear_active_category_cache()` 在分类变更后递增缓存版本号。 |
| [secondhand-platform/catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L62) | 62-83 | `get_active_category_ids()` 把启用分类 ID 列表写入 Redis 动态 key。 |
| [secondhand-platform/catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L86) | 86-100 | 使用 Redis 版本号生成动态缓存 key，避免每次读取前查询数据库聚合状态。 |
| [secondhand-platform/catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L103) | 103-113 | `get_active_categories()` 改为复用缓存后的分类 ID。 |
| [secondhand-platform/catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L160) | 160-179 | 公开商品列表查询通过缓存后的启用分类 ID 过滤商品。 |
| [secondhand-platform/catalog/signals.py](../secondhand-platform/catalog/signals.py#L10) | 10-14 | 分类保存或删除后清理启用分类缓存。 |
| [secondhand-platform/catalog/apps.py](../secondhand-platform/catalog/apps.py#L9) | 9-13 | 在 `ready()` 中导入 `catalog.signals`，确保信号注册。 |
| [secondhand-platform/catalog/forms.py](../secondhand-platform/catalog/forms.py#L34) | 34-38、160-162 | 商品发布/筛选表单继续从 `get_active_categories()` 获取启用分类，因此自动走缓存路径。 |

## 私信数据模型与迁移

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [secondhand-platform/messaging/models.py](../secondhand-platform/messaging/models.py#L6) | 6-43 | 新增 `Conversation` 会话模型，记录两个参与者、创建时间、更新时间。 |
| [secondhand-platform/messaging/models.py](../secondhand-platform/messaging/models.py#L35) | 35-39 | 对会话参与者增加唯一约束与顺序约束，避免 A-B 与 B-A 形成重复会话。 |
| [secondhand-platform/messaging/models.py](../secondhand-platform/messaging/models.py#L46) | 46-58 | 提供参与者判断与获取对方参与者的模型方法。 |
| [secondhand-platform/messaging/models.py](../secondhand-platform/messaging/models.py#L61) | 61-89 | 新增 `PrivateMessage` 消息模型，记录会话、发送者、内容、已读时间、创建时间。 |
| [secondhand-platform/messaging/migrations/0001_initial.py](../secondhand-platform/messaging/migrations/0001_initial.py#L17) | 17-29 | 创建 `Conversation` 表。 |
| [secondhand-platform/messaging/migrations/0001_initial.py](../secondhand-platform/messaging/migrations/0001_initial.py#L32) | 32-45 | 创建 `PrivateMessage` 表。 |
| [secondhand-platform/messaging/migrations/0001_initial.py](../secondhand-platform/messaging/migrations/0001_initial.py#L48) | 48-70 | 增加会话和消息索引、唯一约束、顺序约束。 |

## 私信业务层、查询层与表单

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [secondhand-platform/messaging/services.py](../secondhand-platform/messaging/services.py#L8) | 8 | 定义单条私信最大长度 `1000`。 |
| [secondhand-platform/messaging/services.py](../secondhand-platform/messaging/services.py#L11) | 11-25 | `get_or_create_conversation()` 创建或复用两人会话，并按用户 ID 固定参与者顺序。 |
| [secondhand-platform/messaging/services.py](../secondhand-platform/messaging/services.py#L28) | 28-46 | `create_private_message()` 校验参与者与内容，并在事务内创建消息、更新会话时间。 |
| [secondhand-platform/messaging/services.py](../secondhand-platform/messaging/services.py#L49) | 49-58 | `mark_conversation_read()` 将当前用户收到的未读消息标记为已读。 |
| [secondhand-platform/messaging/services.py](../secondhand-platform/messaging/services.py#L61) | 61-74 | `serialize_private_message()` 给 WebSocket 返回前端所需的消息 JSON。 |
| [secondhand-platform/messaging/services.py](../secondhand-platform/messaging/services.py#L77) | 77-98 | 集中处理登录用户、会话参与者、消息内容和用户 ID 校验。 |
| [secondhand-platform/messaging/selectors.py](../secondhand-platform/messaging/selectors.py#L7) | 7-26 | `get_user_conversations()` 查询用户参与的会话并聚合未读数。 |
| [secondhand-platform/messaging/selectors.py](../secondhand-platform/messaging/selectors.py#L29) | 29-32 | `get_conversation_for_user()` 限制非参与者访问会话。 |
| [secondhand-platform/messaging/selectors.py](../secondhand-platform/messaging/selectors.py#L35) | 35-39 | `get_conversation_messages()` 预加载发送者与资料，避免模板 N+1 查询。 |
| [secondhand-platform/messaging/forms.py](../secondhand-platform/messaging/forms.py#L7) | 7-23 | 新增 `PrivateMessageForm`，校验空内容和长度。 |

## 私信 HTTP 与 WebSocket

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [secondhand-platform/messaging/urls.py](../secondhand-platform/messaging/urls.py#L9) | 9-21 | 定义私信列表、开始会话、会话详情三个 HTTP 路由。 |
| [secondhand-platform/messaging/views.py](../secondhand-platform/messaging/views.py#L24) | 24-39 | `ConversationListView` 作为 `/messages/` 入口；有会话时直达最近会话详情，无会话时保留空列表页。 |
| [secondhand-platform/messaging/views.py](../secondhand-platform/messaging/views.py#L33) | 33-46 | `StartConversationView` 从商品详情或卖家主页发起会话。 |
| [secondhand-platform/messaging/views.py](../secondhand-platform/messaging/views.py#L49) | 49-96 | `ConversationDetailView` 展示会话、标记已读，并保留 HTTP POST 发送消息作为 WebSocket 失败时的回退路径。 |
| [secondhand-platform/messaging/routing.py](../secondhand-platform/messaging/routing.py#L5) | 5-7 | 定义 `/ws/messages/<conversation_id>/` WebSocket 路由。 |
| [secondhand-platform/messaging/consumers.py](../secondhand-platform/messaging/consumers.py#L13) | 13-32 | `PrivateMessageConsumer` 连接时校验登录和会话参与者权限，并加入会话群组。 |
| [secondhand-platform/messaging/consumers.py](../secondhand-platform/messaging/consumers.py#L36) | 36-58 | 接收 JSON 消息，创建私信后通过 channel layer 广播给会话双方。 |
| [secondhand-platform/messaging/consumers.py](../secondhand-platform/messaging/consumers.py#L61) | 61-78 | 向前端发送消息事件，并封装数据库访问。 |
| [secondhand-platform/messaging/admin.py](../secondhand-platform/messaging/admin.py#L6) | 6-64 | 注册会话和消息后台管理，列表中只展示消息摘要。 |

## 私信入口直达会话详情调整

| 文件 | 行号 | 后端变更 |
| --- | --- | --- |
| [secondhand-platform/messaging/urls.py](../secondhand-platform/messaging/urls.py#L11) | 11-12 | `/messages/` 继续保留为 `conversation_list` 命名入口，顶部“私信”导航无需改 URL。 |
| [secondhand-platform/messaging/views.py](../secondhand-platform/messaging/views.py#L24) | 24-30 | `ConversationListView` 继续复用 `get_user_conversations()` 作为当前用户会话来源。 |
| [secondhand-platform/messaging/views.py](../secondhand-platform/messaging/views.py#L32) | 32-38 | `ConversationListView.get()` 取第一条会话；存在会话时重定向到 `messaging:conversation_detail`，跳过中间列表页。 |
| [secondhand-platform/messaging/views.py](../secondhand-platform/messaging/views.py#L39) | 39 | 当用户没有任何会话时，才回退到原列表页空状态，避免 `/messages/` 无目标会话时报错。 |
| [secondhand-platform/messaging/selectors.py](../secondhand-platform/messaging/selectors.py#L7) | 7-33 | `get_user_conversations()` 按 `-updated_at, -id` 排序，因此 `ConversationListView.get()` 的第一条会话就是最近会话。 |
| [secondhand-platform/messaging/selectors.py](../secondhand-platform/messaging/selectors.py#L10) | 10-30 | 会话查询同时注解最近消息内容与时间，供详情页左侧“最近会话”列表复用。 |
| [secondhand-platform/messaging/views.py](../secondhand-platform/messaging/views.py#L97) | 97-105 | `ConversationDetailView.get_context_data()` 向详情页提供当前会话、会话列表、对方用户、消息列表和发送表单，支撑直达后的双栏私信工作台。 |

## 页面入口与模板

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [secondhand-platform/templates/base.html](../secondhand-platform/templates/base.html#L413) | 413 | 登录后的顶部导航新增“私信”入口。 |
| [secondhand-platform/templates/catalog/listing_detail.html](../secondhand-platform/templates/catalog/listing_detail.html#L381) | 381-386 | 商品详情页新增“联系卖家 / 登录后私信”入口。 |
| [secondhand-platform/templates/users/public_profile.html](../secondhand-platform/templates/users/public_profile.html#L196) | 196-201 | 卖家主页新增“联系卖家 / 登录后私信”入口。 |
| [secondhand-platform/templates/messaging/conversation_list.html](../secondhand-platform/templates/messaging/conversation_list.html#L67) | 67-105 | 新增私信列表页，展示会话、未读数、空状态和分页。 |
| [secondhand-platform/templates/messaging/conversation_detail.html](../secondhand-platform/templates/messaging/conversation_detail.html#L82) | 82-115 | 新增会话详情页，展示消息列表、表单和返回入口。 |
| [secondhand-platform/templates/messaging/conversation_detail.html](../secondhand-platform/templates/messaging/conversation_detail.html#L121) | 121-187 | 新增浏览器端 WebSocket 逻辑，发送消息、接收广播并更新 DOM。 |

## 测试覆盖

| 文件 | 行号 | 覆盖点 |
| --- | --- | --- |
| [secondhand-platform/messaging/tests.py](../secondhand-platform/messaging/tests.py#L66) | 66-114 | 会话创建、消息创建、权限校验、已读标记。 |
| [secondhand-platform/messaging/tests.py](../secondhand-platform/messaging/tests.py#L117) | 117-133 | 会话查询和非参与者访问限制。 |
| [secondhand-platform/messaging/tests.py](../secondhand-platform/messaging/tests.py#L136) | 136-149 | Admin 注册与消息摘要展示。 |
| [secondhand-platform/messaging/tests.py](../secondhand-platform/messaging/tests.py#L153) | 153-226 | 私信页面登录限制、入口展示、开始会话、详情页、HTTP 回退发送。 |
| [secondhand-platform/messaging/tests.py](../secondhand-platform/messaging/tests.py#L229) | 229-245 | 分类缓存写入与分类保存后的缓存失效。 |
| [secondhand-platform/messaging/tests.py](../secondhand-platform/messaging/tests.py#L248) | 248-300 | WebSocket 发送消息与非参与者拒绝连接。 |

## 已执行验证

- `uv run python secondhand-platform\manage.py check`：通过。
- `uv run python secondhand-platform\manage.py shell -c "from django.core.cache import cache; ..."`：通过，Django cache 写入并从 Redis 容器读回 `ok`。
- `uv run python secondhand-platform\manage.py makemigrations --check --dry-run`：通过，无遗漏迁移。
- `uv run python secondhand-platform\manage.py test messaging --keepdb`：通过，17 个测试。
- `uv run python secondhand-platform\manage.py test catalog --keepdb`：通过，156 个测试。
- `uv run python secondhand-platform\manage.py test interactions --keepdb`：通过，56 个测试。
- `uv run python secondhand-platform\manage.py test orders --keepdb`：通过，111 个测试。
- `uv run python secondhand-platform\manage.py test users --keepdb`：通过，49 个测试。
- 多测试进程并行运行时，共用 PostgreSQL 测试库 `test_secondhand_platform` 与 `--keepdb` 会出现死锁，因此已改为顺序测试。

## 审查注意事项

- `_bmad-output/` 目录被 `.gitignore` 忽略，相关 PRD、架构、Story 和 sprint 文档变更不会出现在普通 `git status` 中。
- `.env` 被 `.gitignore` 忽略。本次没有把 `.env` 中的敏感值写入文档或提交内容。
- 本地 Redis 默认端口已经从 `6379` 调整为 `6380`；如果后续 Docker 端口映射改变，只需要通过 `.env` 增加对应 Redis URL 覆盖，或同步修改上述默认值。

## 2026-06-11 代码注释与分类缓存优化补充

### 变更总览

- 补齐非测试、非迁移业务代码中的函数 docstring，覆盖 catalog、interactions、messaging、orders、users 相关模块。
- 将 catalog 启用分类 Redis 缓存调整为“版本号动态 key”方案，分类启用、停用、新增或删除后通过 signal 递增版本号，使旧 key 自动失效。
- 合并 messaging 中重复的错误消息提取逻辑，由 `messaging.services.first_error_message()` 统一提供。
- 删除或简化部分不必要逻辑，包括订单服务中的不可达空值判断、互动服务中的冗余布尔分支、Django 脚手架遗留注释。
- 更新缓存相关测试与 Redis/Channels 审查文档，确保实现、测试和文档一致。

### 行级变更明细

#### 项目约束

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [AGENTS.md](../AGENTS.md#L3) | 3 | 增加代码结构和注释质量要求。 |

#### catalog

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L9) | 9-11 | 定义启用分类缓存数据 key 前缀、版本号 key 和缓存 TTL。 |
| [catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L49) | 49-59 | `clear_active_category_cache()` 改为递增 Redis 版本号，分类变更后切换到新的动态 key。 |
| [catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L62) | 62-83 | `get_active_category_ids()` 使用当前版本动态 key 缓存启用分类 ID。 |
| [catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L86) | 86-94 | `_active_category_ids_cache_key()` 由 Redis 版本号生成动态缓存 key，避免每次读取前做数据库聚合。 |
| [catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L97) | 97-100 | `_new_category_cache_version()` 使用 `time_ns()` 生成低碰撞版本号。 |
| [catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L103) | 103-113 | `get_active_categories()` 补充 docstring，并继续返回可链式使用的 QuerySet。 |
| [catalog/selectors.py](../secondhand-platform/catalog/selectors.py#L160) | 160-207 | `get_publish_listing_queryset()` 补充 docstring，并简化关键词、商品类型筛选判断。 |
| [catalog/admin.py](../secondhand-platform/catalog/admin.py#L56) | 56-74 | 为后台商品查询、图片数量和交付说明摘要函数补充 docstring。 |
| [catalog/forms.py](../secondhand-platform/catalog/forms.py#L32) | 32-58 | 为商品表单初始化、价格校验和类型差异字段清理函数补充 docstring。 |
| [catalog/forms.py](../secondhand-platform/catalog/forms.py#L84) | 84-95 | 为商品图片大小校验函数补充 docstring。 |
| [catalog/forms.py](../secondhand-platform/catalog/forms.py#L136) | 136-215 | 为商品筛选表单及关键词、价格、页码、区间校验函数补充 docstring。 |
| [catalog/models.py](../secondhand-platform/catalog/models.py#L9) | 9-27 | 为 `Category` 及其 `__str__()` 补充说明。 |
| [catalog/models.py](../secondhand-platform/catalog/models.py#L37) | 37-134 | 为 `Listing` 及其 `__str__()` 补充说明。 |
| [catalog/models.py](../secondhand-platform/catalog/models.py#L144) | 144-171 | 为 `ListingImage` 及其 `__str__()` 补充说明。 |
| [catalog/services.py](../secondhand-platform/catalog/services.py#L65) | 65-69 | 为事务提交后的图片文件清理闭包补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L45) | 45-82 | 为商品创建页 GET、POST 和上下文构造函数补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L100) | 100-158 | 为商品编辑页读取、GET、POST 和上下文函数补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L170) | 170-191 | 为商品删除页读取、确认页和删除动作补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L202) | 202-210 | 为卖家商品分组列表页补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L225) | 225-246 | 为商品状态更新的 405 响应和 POST 动作补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L250) | 250-321 | 为公开商品列表、分页、上下文和筛选摘要函数补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L325) | 325-401 | 为商品详情查询和详情上下文补充 docstring。 |
| [catalog/views.py](../secondhand-platform/catalog/views.py#L410) | 410-450 | 为购买确认页读取商品、上下文、GET 和 POST 函数补充 docstring。 |

#### interactions

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [interactions/admin.py](../secondhand-platform/interactions/admin.py#L6) | 6-24 | 为回复筛选器及其选项、查询函数补充 docstring。 |
| [interactions/admin.py](../secondhand-platform/interactions/admin.py#L31) | 31-64 | 为留言后台、内容摘要和回复判断函数补充 docstring，并把回复判断简化为布尔表达式。 |
| [interactions/forms.py](../secondhand-platform/interactions/forms.py#L19) | 19-26 | 为留言内容清理函数补充 docstring。 |
| [interactions/models.py](../secondhand-platform/interactions/models.py#L6) | 6-51 | 为 `Comment` 模型和 `__str__()` 补充说明。 |
| [interactions/services.py](../secondhand-platform/interactions/services.py#L37) | 37-42 | 简化 `can_interact_with_listing()` 的冗余布尔分支。 |
| [interactions/views.py](../secondhand-platform/interactions/views.py#L13) | 13-43 | 删除脚手架注释，并为顶层留言创建视图和 POST 函数补充 docstring。 |
| [interactions/views.py](../secondhand-platform/interactions/views.py#L47) | 47-64 | 为留言删除视图和 POST 函数补充 docstring。 |
| [interactions/views.py](../secondhand-platform/interactions/views.py#L85) | 85-116 | 为二级留言回复视图和 POST 函数补充 docstring。 |

#### messaging

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [messaging/admin.py](../secondhand-platform/messaging/admin.py#L6) | 6-20 | 为私信内联后台和内容摘要函数补充 docstring。 |
| [messaging/admin.py](../secondhand-platform/messaging/admin.py#L24) | 24-49 | 为会话后台和消息数量函数补充 docstring。 |
| [messaging/admin.py](../secondhand-platform/messaging/admin.py#L53) | 53-77 | 为私信后台和内容摘要函数补充 docstring。 |
| [messaging/consumers.py](../secondhand-platform/messaging/consumers.py#L14) | 14-88 | 为 WebSocket 连接、断开、收消息、广播和数据库包装函数补充 docstring，并复用统一错误消息函数。 |
| [messaging/forms.py](../secondhand-platform/messaging/forms.py#L20) | 20-27 | 为私信内容清理函数补充 docstring。 |
| [messaging/models.py](../secondhand-platform/messaging/models.py#L6) | 6-69 | 为会话模型、参与者字段、约束、`__str__()`、参与者判断和对方参与者读取函数补充说明。 |
| [messaging/models.py](../secondhand-platform/messaging/models.py#L76) | 76-115 | 为私信模型、字段、索引和 `__str__()` 补充说明。 |
| [messaging/selectors.py](../secondhand-platform/messaging/selectors.py#L7) | 7-49 | 为会话列表、单会话权限读取和消息列表查询函数补充 docstring。 |
| [messaging/services.py](../secondhand-platform/messaging/services.py#L77) | 77-84 | 新增 `first_error_message()`，统一提取可展示错误消息。 |
| [messaging/services.py](../secondhand-platform/messaging/services.py#L88) | 88-108 | 为登录校验、会话参与者校验和私信内容清理函数补充 docstring。 |
| [messaging/views.py](../secondhand-platform/messaging/views.py#L25) | 25-44 | 为会话入口页、查询函数和直达最近会话逻辑补充 docstring。 |
| [messaging/views.py](../secondhand-platform/messaging/views.py#L49) | 49-68 | 为发起私信视图、GET 拒绝和 POST 创建会话函数补充 docstring，并复用统一错误消息函数。 |
| [messaging/views.py](../secondhand-platform/messaging/views.py#L71) | 71-126 | 为会话详情页、会话读取、GET、POST 和上下文函数补充 docstring，并复用统一错误消息函数。 |
| [messaging/tests.py](../secondhand-platform/messaging/tests.py#L249) | 249-268 | 更新 Redis 分类缓存测试，断言版本号动态 key 变更和新 key 重新写入。 |

#### orders

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [orders/models.py](../secondhand-platform/orders/models.py#L6) | 6-22 | 为订单模型和订单状态枚举补充说明。 |
| [orders/models.py](../secondhand-platform/orders/models.py#L75) | 75-78 | 为订单 `__str__()` 补充说明。 |
| [orders/selectors.py](../secondhand-platform/orders/selectors.py#L4) | 4-24 | 为买家订单和卖家订单查询函数补充 docstring。 |
| [orders/services.py](../secondhand-platform/orders/services.py#L92) | 92-128 | 删除卖家确认发货流程中取到 `Listing` 后再次判断空值的不可达逻辑。 |
| [orders/services.py](../secondhand-platform/orders/services.py#L136) | 136-169 | 删除买家确认收货流程中取到 `Listing` 后再次判断空值的不可达逻辑。 |
| [orders/tasks.py](../secondhand-platform/orders/tasks.py#L12) | 12-31 | 为三个 Celery 订单任务函数补充 docstring。 |
| [orders/views.py](../secondhand-platform/orders/views.py#L18) | 18-38 | 为订单详情视图和 GET 函数补充 docstring。 |
| [orders/views.py](../secondhand-platform/orders/views.py#L42) | 42-57 | 为订单支付视图和 POST 函数补充 docstring。 |
| [orders/views.py](../secondhand-platform/orders/views.py#L61) | 61-79 | 为买家订单列表查询和上下文函数补充 docstring。 |
| [orders/views.py](../secondhand-platform/orders/views.py#L82) | 82-100 | 为卖家订单列表查询和上下文函数补充 docstring。 |
| [orders/views.py](../secondhand-platform/orders/views.py#L103) | 103-121 | 为卖家确认发货视图和 POST 函数补充 docstring。 |
| [orders/views.py](../secondhand-platform/orders/views.py#L124) | 124-140 | 为买家确认收货视图和 POST 函数补充 docstring。 |

#### users

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| [users/views.py](../secondhand-platform/users/views.py#L180) | 180-208 | 为卖家公开主页视图和 GET 函数补充 docstring。 |

### 验证记录

| 命令 | 结果 |
| --- | --- |
| `python manage.py check` | 通过，`System check identified no issues`。 |
| `python -m compileall secondhand-platform` | 通过。 |
| `python manage.py test messaging --keepdb` | 通过，17 个测试。 |
| `python manage.py test catalog --keepdb` | 通过，156 个测试。 |
| `python manage.py test interactions --keepdb` | 通过，56 个测试。 |
| `python manage.py test orders --keepdb` | 通过，111 个测试。 |
| `python manage.py test users --keepdb` | 通过，49 个测试。 |
| `git diff --check` | 通过，仅存在 Git 对 LF/CRLF 的换行提示。 |

### Git 提交注释

```text
refactor: 补齐代码注释并优化分类缓存

- 为非测试、非迁移业务代码补齐中文函数 docstring
- 将 catalog 启用分类缓存优化为 Redis 版本号动态 key
- 分类保存或删除后递增缓存版本号，使启用/停用变更立即切换缓存 key
- 合并 messaging 错误消息提取逻辑，复用 first_error_message()
- 删除订单服务中的不可达空值判断，简化互动模块冗余布尔逻辑
- 更新缓存相关测试和 docs 变更说明，补充本次变更行级链接
- 通过 Django check、compileall、catalog/messaging/interactions/orders/users 测试
```

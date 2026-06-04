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
| `secondhand-platform/config/settings/base.py` | 24 | 注册 `daphne`，让 ASGI 服务支持 Channels。 |
| `secondhand-platform/config/settings/base.py` | 35 | 注册 `messaging.apps.MessagingConfig`。 |
| `secondhand-platform/config/settings/base.py` | 68 | 设置 `ASGI_APPLICATION = "config.asgi.application"`。 |
| `secondhand-platform/config/settings/base.py` | 132-135 | Django Cache 与 Channels 的默认 Redis 连接改为 `redis://localhost:6380/2` 和 `redis://localhost:6380/3`，对应 `secondhand-platform-redis` 容器的宿主机端口。 |
| `secondhand-platform/config/settings/base.py` | 137-140 | 使用 Django 内置 Redis cache backend。 |
| `secondhand-platform/config/settings/base.py` | 144-148 | 使用 `channels_redis.core.RedisChannelLayer`，WebSocket 群组消息走 Redis。 |
| `secondhand-platform/config/settings/development.py` | 25-27 | Celery broker/result backend 的开发默认连接改为 `redis://localhost:6380/0` 和 `redis://localhost:6380/1`。 |
| `secondhand-platform/config/settings/production.py` | 25-29 | 生产环境继续强制从环境变量读取 Celery、Cache、Channels Redis URL，不使用本地默认端口。 |

## 依赖与 ASGI 入口

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| `pyproject.toml` | 8-9 | 新增 `channels[daphne]>=4,<5`、`channels-redis>=4,<5`。 |
| `uv.lock` | 182-211 | 锁定 `channels` 与 `channels-redis` 依赖。 |
| `uv.lock` | 335-345 | 锁定 `daphne`。 |
| `uv.lock` | 624-651 | 锁定 `redis` 包，并把 Channels 依赖写入项目依赖清单。 |
| `secondhand-platform/config/asgi.py` | 12-14 | 引入 Channels 的认证、路由和 Host 校验组件。 |
| `secondhand-platform/config/asgi.py` | 21 | 引入 `messaging.routing.websocket_urlpatterns`。 |
| `secondhand-platform/config/asgi.py` | 23-28 | 使用 `ProtocolTypeRouter` 同时提供 HTTP 与 WebSocket 协议入口。 |
| `secondhand-platform/config/urls.py` | 18 | 挂载 `/messages/` 到 `messaging.urls`。 |

## 分类 Redis 缓存

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| `secondhand-platform/catalog/selectors.py` | 4 | 引入 `django.core.cache.cache`。 |
| `secondhand-platform/catalog/selectors.py` | 8-9 | 定义启用分类 ID 的缓存 key 与 10 分钟超时时间。 |
| `secondhand-platform/catalog/selectors.py` | 47-50 | 新增 `clear_active_category_cache()`，用于主动清理分类缓存。 |
| `secondhand-platform/catalog/selectors.py` | 53-78 | 新增 `get_active_category_ids()`，把启用分类 ID 列表写入 Redis 缓存。 |
| `secondhand-platform/catalog/selectors.py` | 81-88 | 使用分类总数与最新更新时间生成版本化缓存 key，降低旧缓存命中风险。 |
| `secondhand-platform/catalog/selectors.py` | 92-95 | `get_active_categories()` 改为复用缓存后的分类 ID。 |
| `secondhand-platform/catalog/selectors.py` | 142-149 | 公开商品列表查询通过缓存后的启用分类 ID 过滤商品。 |
| `secondhand-platform/catalog/signals.py` | 10-14 | 分类保存或删除后清理启用分类缓存。 |
| `secondhand-platform/catalog/apps.py` | 9-13 | 在 `ready()` 中导入 `catalog.signals`，确保信号注册。 |
| `secondhand-platform/catalog/forms.py` | 34-38、160-162 | 商品发布/筛选表单继续从 `get_active_categories()` 获取启用分类，因此自动走缓存路径。 |

## 私信数据模型与迁移

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| `secondhand-platform/messaging/models.py` | 6-43 | 新增 `Conversation` 会话模型，记录两个参与者、创建时间、更新时间。 |
| `secondhand-platform/messaging/models.py` | 35-39 | 对会话参与者增加唯一约束与顺序约束，避免 A-B 与 B-A 形成重复会话。 |
| `secondhand-platform/messaging/models.py` | 46-58 | 提供参与者判断与获取对方参与者的模型方法。 |
| `secondhand-platform/messaging/models.py` | 61-89 | 新增 `PrivateMessage` 消息模型，记录会话、发送者、内容、已读时间、创建时间。 |
| `secondhand-platform/messaging/migrations/0001_initial.py` | 17-29 | 创建 `Conversation` 表。 |
| `secondhand-platform/messaging/migrations/0001_initial.py` | 32-45 | 创建 `PrivateMessage` 表。 |
| `secondhand-platform/messaging/migrations/0001_initial.py` | 48-70 | 增加会话和消息索引、唯一约束、顺序约束。 |

## 私信业务层、查询层与表单

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| `secondhand-platform/messaging/services.py` | 8 | 定义单条私信最大长度 `1000`。 |
| `secondhand-platform/messaging/services.py` | 11-25 | `get_or_create_conversation()` 创建或复用两人会话，并按用户 ID 固定参与者顺序。 |
| `secondhand-platform/messaging/services.py` | 28-46 | `create_private_message()` 校验参与者与内容，并在事务内创建消息、更新会话时间。 |
| `secondhand-platform/messaging/services.py` | 49-58 | `mark_conversation_read()` 将当前用户收到的未读消息标记为已读。 |
| `secondhand-platform/messaging/services.py` | 61-74 | `serialize_private_message()` 给 WebSocket 返回前端所需的消息 JSON。 |
| `secondhand-platform/messaging/services.py` | 77-98 | 集中处理登录用户、会话参与者、消息内容和用户 ID 校验。 |
| `secondhand-platform/messaging/selectors.py` | 7-26 | `get_user_conversations()` 查询用户参与的会话并聚合未读数。 |
| `secondhand-platform/messaging/selectors.py` | 29-32 | `get_conversation_for_user()` 限制非参与者访问会话。 |
| `secondhand-platform/messaging/selectors.py` | 35-39 | `get_conversation_messages()` 预加载发送者与资料，避免模板 N+1 查询。 |
| `secondhand-platform/messaging/forms.py` | 7-23 | 新增 `PrivateMessageForm`，校验空内容和长度。 |

## 私信 HTTP 与 WebSocket

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| `secondhand-platform/messaging/urls.py` | 9-21 | 定义私信列表、开始会话、会话详情三个 HTTP 路由。 |
| `secondhand-platform/messaging/views.py` | 24-31 | `ConversationListView` 展示当前用户会话列表。 |
| `secondhand-platform/messaging/views.py` | 33-46 | `StartConversationView` 从商品详情或卖家主页发起会话。 |
| `secondhand-platform/messaging/views.py` | 49-96 | `ConversationDetailView` 展示会话、标记已读，并保留 HTTP POST 发送消息作为 WebSocket 失败时的回退路径。 |
| `secondhand-platform/messaging/routing.py` | 5-7 | 定义 `/ws/messages/<conversation_id>/` WebSocket 路由。 |
| `secondhand-platform/messaging/consumers.py` | 13-32 | `PrivateMessageConsumer` 连接时校验登录和会话参与者权限，并加入会话群组。 |
| `secondhand-platform/messaging/consumers.py` | 36-58 | 接收 JSON 消息，创建私信后通过 channel layer 广播给会话双方。 |
| `secondhand-platform/messaging/consumers.py` | 61-78 | 向前端发送消息事件，并封装数据库访问。 |
| `secondhand-platform/messaging/admin.py` | 6-64 | 注册会话和消息后台管理，列表中只展示消息摘要。 |

## 页面入口与模板

| 文件 | 行号 | 变更 |
| --- | --- | --- |
| `secondhand-platform/templates/base.html` | 413 | 登录后的顶部导航新增“私信”入口。 |
| `secondhand-platform/templates/catalog/listing_detail.html` | 381-386 | 商品详情页新增“联系卖家 / 登录后私信”入口。 |
| `secondhand-platform/templates/users/public_profile.html` | 196-201 | 卖家主页新增“联系卖家 / 登录后私信”入口。 |
| `secondhand-platform/templates/messaging/conversation_list.html` | 67-105 | 新增私信列表页，展示会话、未读数、空状态和分页。 |
| `secondhand-platform/templates/messaging/conversation_detail.html` | 82-115 | 新增会话详情页，展示消息列表、表单和返回入口。 |
| `secondhand-platform/templates/messaging/conversation_detail.html` | 121-187 | 新增浏览器端 WebSocket 逻辑，发送消息、接收广播并更新 DOM。 |

## 测试覆盖

| 文件 | 行号 | 覆盖点 |
| --- | --- | --- |
| `secondhand-platform/messaging/tests.py` | 66-114 | 会话创建、消息创建、权限校验、已读标记。 |
| `secondhand-platform/messaging/tests.py` | 117-133 | 会话查询和非参与者访问限制。 |
| `secondhand-platform/messaging/tests.py` | 136-149 | Admin 注册与消息摘要展示。 |
| `secondhand-platform/messaging/tests.py` | 153-226 | 私信页面登录限制、入口展示、开始会话、详情页、HTTP 回退发送。 |
| `secondhand-platform/messaging/tests.py` | 229-245 | 分类缓存写入与分类保存后的缓存失效。 |
| `secondhand-platform/messaging/tests.py` | 248-300 | WebSocket 发送消息与非参与者拒绝连接。 |

## 已执行验证

- `uv run python secondhand-platform\manage.py check`：通过。
- `uv run python secondhand-platform\manage.py shell -c "from django.core.cache import cache; ..."`：通过，Django cache 写入并从 Redis 容器读回 `ok`。
- `uv run python secondhand-platform\manage.py makemigrations --check --dry-run`：通过，无遗漏迁移。
- `uv run python secondhand-platform\manage.py test messaging --keepdb`：通过，16 个测试。
- `uv run python secondhand-platform\manage.py test catalog --keepdb`：通过，156 个测试。
- `uv run python secondhand-platform\manage.py test interactions --keepdb`：通过，56 个测试。
- `uv run python secondhand-platform\manage.py test orders --keepdb`：通过，111 个测试。
- `uv run python secondhand-platform\manage.py test users --keepdb`：通过，49 个测试。
- 多测试进程并行运行时，共用 PostgreSQL 测试库 `test_secondhand_platform` 与 `--keepdb` 会出现死锁，因此已改为顺序测试。

## 审查注意事项

- `_bmad-output/` 目录被 `.gitignore` 忽略，相关 PRD、架构、Story 和 sprint 文档变更不会出现在普通 `git status` 中。
- `.env` 被 `.gitignore` 忽略。本次没有把 `.env` 中的敏感值写入文档或提交内容。
- 本地 Redis 默认端口已经从 `6379` 调整为 `6380`；如果后续 Docker 端口映射改变，只需要通过 `.env` 增加对应 Redis URL 覆盖，或同步修改上述默认值。

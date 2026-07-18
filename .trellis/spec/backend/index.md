# 后端开发规范

本目录描述 `backend/` Django 服务的实际结构、数据访问、错误处理、日志和质量要求。项目是单仓库，前端在 `frontend/`，跨层变更同时参考 `../guides/cross-layer-thinking-guide.md`。

## 开发前检查清单

1. 确认需求属于哪个业务 app，并先阅读对应的 `models.py`、`serializers.py`、`selectors.py`、`services.py` 和测试。
2. 搜索是否已有同类 selector/service、缓存键、错误消息和前端 endpoint。
3. 若修改模型，检查 migration、索引、快照字段和订单状态联动。
4. 若修改 API，确认 JWT 权限、分页、`message/errors` 错误契约和前端类型。
5. 若修改 WebSocket 或 Celery，检查异步边界、Redis 限流/缓存以及 `on_commit` 副作用。

## 规范索引

| 文档 | 适用场景 |
|---|---|
| [目录与模块结构](./directory-structure.md) | 新增 app、模块或文件 |
| [数据库与 ORM](./database-guidelines.md) | 模型、查询、迁移、事务和缓存 |
| [错误处理](./error-handling.md) | API、service、WebSocket 异常 |
| [日志](./logging-guidelines.md) | 诊断、降级和敏感信息 |
| [质量与测试](./quality-guidelines.md) | 实现完成后的测试和检查 |

## 质量检查

完成修改后执行：

```powershell
uv run pytest
uv run python backend/manage.py check
```

前后端接口或类型同时变化时，再执行：

```powershell
cd frontend
npm run lint
npm run build
```

无法连接 PostgreSQL 或 Redis 时，应说明环境限制，并至少运行不依赖外部服务的静态检查和单元测试。

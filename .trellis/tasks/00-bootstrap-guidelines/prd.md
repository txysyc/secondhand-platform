# 生成项目第一版 Trellis 规范

## 目标

根据当前二手交易平台代码库，为后续 Django、DRF、Channels、Celery、React、TypeScript 和跨层任务提供可追溯到真实源文件的 `.trellis/spec/` 指南。

## 范围

- 后端目录：`backend/`
- 后端规范：目录结构、数据库与 ORM、错误处理、日志、质量与测试。
- 前端目录：`frontend/`
- 前端规范：目录结构、API 与类型契约、组件/状态/路由、质量与验证。
- 共享指南：代码复用、跨层数据流，以及共享索引。
- 参考代码：`config/`、`api/`、`users/`、`catalog/`、`orders/`、`interactions/`、`messaging/`、`notifications/` 和各 app 的 `tests/`。
- 不新增依赖；本次允许修复现有前端 lint 问题，规范必须记录当前代码而不是未落地的重构目标。

## 已确认的架构事实

- Django 6 + DRF，以按业务域拆分的 app 组织代码。
- `selectors.py` 负责只读查询，`services.py` 负责业务写入、事务和状态流转，`views.py` 负责 API 编排。
- PostgreSQL 是主数据库，Redis 用于 Django 缓存和 Channels，Celery 负责订单超时/自动完成任务。
- API 错误由 `api.exceptions.api_exception_handler` 统一包装为 `message/errors`；前端通过 `frontend/src/api/client.ts` 消费该契约。
- 前端采用 React 19、TypeScript、Vite 和 React Router，认证由 `AuthProvider` 管理，业务 API 按域拆分到 `src/api/endpoints/`。

## 产出文件

- `.trellis/spec/backend/index.md`
- `.trellis/spec/backend/directory-structure.md`
- `.trellis/spec/backend/database-guidelines.md`
- `.trellis/spec/backend/error-handling.md`
- `.trellis/spec/backend/logging-guidelines.md`
- `.trellis/spec/backend/quality-guidelines.md`
- `.trellis/spec/frontend/index.md`
- `.trellis/spec/frontend/directory-structure.md`
- `.trellis/spec/frontend/api-and-types.md`
- `.trellis/spec/frontend/ui-and-routing.md`
- `.trellis/spec/frontend/quality-guidelines.md`
- `.trellis/spec/guides/index.md`
- `.trellis/spec/guides/code-reuse-thinking-guide.md`
- `.trellis/spec/guides/cross-layer-thinking-guide.md`

## 验收标准

- [x] 每份指南均包含真实文件路径、项目内示例和适用边界。
- [x] 已移除模板占位文本、空章节和与本项目无关的 Trellis CLI 示例。
- [x] 后端和共享 `index.md` 的链接与文件清单一致。
- [x] 前端 `index.md` 与前端规范文件清单一致。
- [x] 文档与注释使用中文，技术标识符保留代码中的原名。
- [x] `python ./.trellis/scripts/task.py validate 00-bootstrap-guidelines` 通过。
- [x] `uv run python backend/manage.py check` 通过，配置 API 测试 7 项通过。
- [ ] 完整 pytest 未完成：测试库初始化冲突已排除，但完整套件和 `--reuse-db` 运行均在异步/长耗时测试阶段超时。
- [x] 前端 `npm run lint` 和 `npm run build` 均通过，修复了原有 20 个 ESLint 错误。
- [x] 后端质量规范明确要求按模块执行测试，模块过大时再按测试文件拆分。
- [x] 修复共享 `apiClient` 将未填写查询条件序列化为 `undefined`，导致商品、订单和我的商品列表返回 400 的问题。

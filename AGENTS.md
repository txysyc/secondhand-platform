## 项目核心约定

- 这是一个 Django 二手交易平台：后端位于 `backend/`，前端位于 `frontend/`。
- 后端使用 Django、Django REST Framework、Channels、Celery、PostgreSQL 和 Redis。
- 前端使用 React、TypeScript、Vite 和 React Router，通过 `/api/v1/` 与后端通信。
- 代码注释、文档和交互优先使用中文；技术标识符、命令、路径和 API 字段保留原名。
- 所有新增代码遵循现有 Django/React 结构，并为非显然的业务规则添加简短注释。

## 目录职责

- `backend/<app>/models.py`：模型、枚举、约束和模型校验。
- `backend/<app>/serializers.py`：API 输入输出和字段校验。
- `backend/<app>/selectors.py`：只读 QuerySet、可见性、排序和预取。
- `backend/<app>/services.py`：业务动作、权限、事务和状态流转。
- `backend/<app>/views.py`：请求编排和响应，不复制 service 逻辑。
- `frontend/src/api/endpoints/`：按业务域封装 API 请求；`frontend/src/types/`：跨层类型契约。
- `frontend/src/features/`：业务页面；`frontend/src/components/ui/`：无业务含义的通用组件。
- `.agents/`：项目全部 AI skills，允许继续添加新 skill，跨设备同步时保留整个目录。

## 开发验证

```powershell
# 后端系统检查
uv run python backend/manage.py check

# 后端测试优先按 app 执行；模块过大时按测试文件拆分
uv run pytest -q --reuse-db backend/catalog
uv run pytest -q --reuse-db backend/orders/tests/test_07_api.py

# 前端检查
cd frontend
npm run lint
npm run build
```

后端测试长时间无输出时，按模块或测试文件定位；不要并行启动多个会创建同一 PostgreSQL 测试库的 pytest 进程。

## 版本控制边界

- 应提交：`.agents/`、`.codex/`、`.trellis/` 中的 skills、配置、脚本、规范、工作流和工作日志。
- 不应提交：`.trellis/.developer`、`.trellis/.runtime/`、Python 缓存、构建产物和环境文件。
- 工作区存在其他改动时，只提交当前任务范围内的文件，并在提交前明确列出未纳入的路径。

## 人工审查与提交

- 任务实现、自动检查和测试完成后，AI 必须先向用户展示最终变更摘要、测试结果、已知风险以及未纳入提交的路径，然后停止并等待用户审查。用户可能需要阅读代码或执行手动测试，不得因自动检查通过而直接提交。
- 只有用户明确回复“确认提交”或表达同等含义后，AI 才能执行本任务的 `git commit`。任务启动确认、测试命令授权、shell 权限审批和自动审查结果均不等同于提交确认。
- Git 提交流程继续遵循 `.trellis/workflow.md`。业务代码提交完成后，任务归档与 session journal 可以合并为一次 bookkeeping 提交，也可以按实际需要分别提交；无论采用哪种方式，都应在提交计划中明确说明。
- 提交信息使用 Conventional Commits 风格：英文小写类型加中文主题，可选英文 scope，例如 `refactor(catalog): 重构商品视图与缓存`、`chore(task): 归档商品重构任务`。同一任务内保持格式一致。
- 提交内容较多时，首行只写简短总结；空一行后在提交正文中使用中文分点说明主要改动，必要时补充兼容性、测试或迁移信息，避免把所有细节挤在标题中。

<!-- TRELLIS:START -->
# Trellis Instructions

This project is managed by Trellis. The authoritative workflow and working knowledge live under `.trellis/`:

- `.trellis/workflow.md` — the only project AI workflow source
- `.trellis/spec/` — package- and layer-scoped coding guidelines
- `.trellis/tasks/` — task requirements and planning artifacts
- `.trellis/workspace/` — session journals and durable notes

Use the project-local skills under `.agents/skills/` according to the current Trellis workflow stage. Platform adapters under `.codex/` must not override `.trellis/workflow.md`.

<!-- TRELLIS:END -->

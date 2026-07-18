# 前端开发规范

本目录描述 `frontend/` React + TypeScript + Vite 应用的实际组织方式、API 契约、组件与路由约定，以及验证命令。

## 开发前检查清单

1. 确认页面属于哪个 `features/<domain>/`，先阅读相邻页面、endpoint、类型和样式文件。
2. 新增接口前检查 `src/api/client.ts`、`src/api/endpoints/` 和 `src/types/` 是否已有复用类型或请求函数。
3. 修改认证、通知或消息时检查 `AuthProvider`、`Layout` 的 WebSocket/未读数同步和退出清理逻辑。
4. 修改路由时同时检查 `ProtectedRoute`、`AnonymousRoute`、导航链接和登录后回跳行为。
5. 跨后端变更必须阅读 `../guides/cross-layer-thinking-guide.md`，确认 `message/errors`、分页和 ISO 日期契约。

## 规范索引

| 文档 | 适用场景 |
|---|---|
| [目录与模块结构](./directory-structure.md) | 新增页面、组件、类型或样式 |
| [API 与类型契约](./api-and-types.md) | 请求、认证、错误、序列化和后端字段 |
| [组件、状态与路由](./ui-and-routing.md) | React 组件、hooks、路由和实时连接 |
| [质量与验证](./quality-guidelines.md) | lint、TypeScript、构建和手工回归 |

## 质量检查

```powershell
cd frontend
npm run lint
npm run build
```

接口或后端状态流转变化时，还要在仓库根目录运行 `uv run pytest` 与 `uv run python backend/manage.py check`。

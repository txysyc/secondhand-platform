# 前端质量与验证规范

## 必跑命令

在 `frontend/` 目录执行：

```powershell
npm run lint
npm run build
```

`lint` 使用 ESLint 10、TypeScript ESLint、React Hooks 和 React Refresh；`build` 会先执行 `tsc -b`，因此 `noUnusedLocals`、`noUnusedParameters`、`noFallthroughCasesInSwitch` 等 TypeScript 约束必须通过。

## 测试与回归

当前仓库没有 `frontend/tests/` 或组件测试脚手架，新增交互至少要：

- 为 endpoint、类型和后端响应增加可复现的页面手工回归路径。
- 检查 loading、错误、空数据、401 刷新失败、移动端布局和重复点击。
- 若新增测试框架，先在 `package.json`、README 和本规范中记录命令，再按 feature 放置测试。
- 后端 API 或状态机变化同时运行根目录 pytest 与 Django check，确保跨层契约不漂移。

## 禁止事项

- 不使用 `eslint-disable` 或 `as any` 掩盖可修复的类型/依赖问题；现有局部禁用必须说明 React effect 的具体原因。
- 不提交 `frontend/dist/`、临时截图、密钥或本地环境文件。
- 不以 console 日志替代用户可见错误状态；调试日志提交前应删除或改为明确的错误 UI。
- 不为了通过构建删除未使用变量检查或修改 ESLint 全局规则。

## 当前质量基线

`npm run lint` 和 `npm run build` 当前均通过。后续新增代码不得通过 `eslint-disable`、`as any` 或降低全局规则来隐藏类型、Fast Refresh 或 effect 规则问题。

## 提交前清单

- [ ] API endpoint、`types/`、页面和后端字段已同步。
- [ ] 所有异步动作有 loading、错误和重试/恢复路径。
- [ ] 路由守卫、token 清理、WebSocket 关闭和事件监听器均有卸载清理。
- [ ] `npm run lint` 和 `npm run build` 通过。
- [ ] 跨层变更已执行后端 `uv run pytest` 与 `manage.py check`，或记录环境阻塞。

# 组件、状态与路由规范

## 组件设计

- 组件使用函数组件和 TypeScript props 接口；可复用 UI 通过 props 控制状态，不直接读取业务 API。
- `Button` 提供 variant、size、loading、disabled 和 `IconButton`，异步动作必须显示 loading 并禁止重复提交。
- 图标按钮使用 `lucide-react`，同时提供中文 `aria-label`；表单输入应有 label、提示文本和错误提示。
- 页面必须处理 loading、error、empty 和成功状态。商品列表的骨架屏、`EmptyState` 和重试按钮是现有模式。
- 多步或复杂页面按 feature 拆子组件，例如 `ListingForm` 下的 `form/ListingFormFields`、`ListingImageManager`。

## 状态与副作用

- 认证状态只由 `app/providers.tsx:AuthProvider` 管理，页面通过 `useAuth` 访问；不要在每个页面复制 token 读取和用户查询。
- 页面筛选条件优先同步到 URL `searchParams`，保证刷新和分享链接可恢复；修改筛选时重置 page 为 1，参考 `ListingList`。
- `useEffect` 中的异步请求必须处理取消/卸载标记，清理 WebSocket、事件监听器和定时器；`Layout` 的通知连接是完整示例。
- 跨组件未读数使用 `utils/notificationEvents.ts` 的 CustomEvent，并由服务端计数校正，避免本地重复递减。
- 业务状态变更后重新请求或更新完整响应对象，不在前端自行推断后端订单/商品状态机。

## 路由与访问控制

- 路由集中在 `app/router.tsx`；需要登录的页面包裹 `ProtectedRoute`，登录/注册包裹 `AnonymousRoute`。
- `ProtectedRoute` 未登录时跳转 `/login` 并通过 `location.state.from` 保存来源；登录后应回到原路径或首页。
- 新增导航入口要同步 `Layout` 的公开/认证导航、移动端菜单关闭行为和当前路由 active 状态。
- 页面不存在使用 `NotFoundPage`，不要在 feature 内重复实现全局 404。

## 样式与可访问性

- 组件 CSS 放在对应功能样式文件，并由 `styles/index.css` 导入；颜色、间距、圆角优先使用 `tokens.css`。
- 交互控件使用真实 `<button>`、`<a>`、`<form>` 语义元素；图标-only 控件必须有 aria-label，状态提示使用 `role="alert"`。
- 保持现有响应式布局和 `prefers-reduced-motion` 规则，不用内联样式替代可复用 CSS 变量，除非是动态尺寸等确有必要的值。

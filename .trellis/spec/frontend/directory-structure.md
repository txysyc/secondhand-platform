# 前端目录与模块结构

## 目录布局

```text
frontend/src/
├── app/                 # App、Layout、Provider、路由和 404 页面
├── api/
│   ├── client.ts        # fetch 封装、JWT 刷新和统一错误解析
│   └── endpoints/       # 按业务域组织的 HTTP 请求函数
├── types/               # API 响应、表单和 WebSocket 载荷类型
├── components/ui/       # 跨页面基础 UI 组件
├── features/<domain>/   # 按业务域组织的页面和局部组件
├── styles/              # tokens、全局样式和按功能拆分的 CSS
├── utils/               # 媒体 URL、跨组件事件等纯辅助逻辑
└── assets/              # Vite/页面使用的静态资源
```

页面入口集中在 `features/`，不要把业务页面直接放进 `components/ui/`。例如商品域包含 `ListingList.tsx`、`ListingDetail.tsx`、`ListingForm.tsx` 及 `list/`、`detail/`、`form/` 子目录。

## 文件职责

- `app/router.tsx` 只定义路由树和守卫组合；`app/Layout.tsx` 负责全局导航、通知徽标和 WebSocket 生命周期。
- `api/endpoints/*.ts` 只负责请求路径、参数和返回类型，不在其中操作 React state。
- `types/*.ts` 是 API/事件契约的唯一类型来源；页面通过 `import type` 使用。
- `components/ui/` 提供无业务含义的可组合组件（`Button`、`Input`、`Loading`、`Pagination` 等），业务动作通过 props 注入。
- `features/` 页面负责数据加载、局部状态和业务编排；复杂页面可拆到同域子目录。
- `styles/` 以 `index.css` 统一导入；颜色、间距、圆角和动效优先使用 `tokens.css` 的变量。

## 命名与导入

- React 组件和文件使用 PascalCase，endpoint、工具和类型文件使用小写短横线或项目已有命名（如 `notificationEvents.ts`）。
- 组件导出使用具名导出，UI 组件在 `components/ui/index.ts` 汇总导出。
- 类型导入使用 `import type`；不要用 `any` 绕过 API 类型，已有遗留函数应在修改时逐步收窄。
- 新代码注释和用户可见文案使用中文，图标使用项目已安装的 `lucide-react`。

## 反模式

- 在页面里直接拼接重复 API URL、刷新 token 或解析错误 JSON。
- 把商品/订单业务按钮塞进通用 `components/ui/`，造成组件反向依赖 feature。
- 新建全局 CSS 文件却不在 `styles/index.css` 导入，导致生产构建缺少样式。
- 通过相对路径跨越多个 feature 目录共享状态；跨域状态应上移到 `app/providers.tsx` 或提取到明确的 `utils/`。

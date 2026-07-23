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

## Python 与 Django 编码规范

### 代码风格

- 遵循 PEP 8、PEP 257 和现有项目格式；模块、函数与变量使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`。
- 优先使用清晰的领域命名，避免无业务含义的缩写、单字母变量和重复字面量；复杂条件应提取为有语义的变量或函数。
- import 按标准库、第三方库、项目内部模块分组；禁止通配符 import，禁止为绕过循环依赖而在函数内随意 import。
- 保持函数和模块聚焦；发现重复业务规则时先搜索已有 selector、service、validator、枚举或公共 helper，不复制实现。
- 不保留死代码、注释掉的代码、调试 `print()`、无主 TODO 或未使用依赖；日志统一使用 `logging.getLogger(__name__)`。

### 函数设计

- 一个函数只承担一个明确职责，输入、输出和副作用应可从名称与签名判断；视图、Celery task 和 WebSocket consumer 保持为薄编排层。
- 优先使用早返回降低嵌套；复杂分支拆分为具名 helper，但不要为单行表达式制造无意义抽象。
- 参数应显式且数量适中；禁止用布尔参数隐藏两套不相关行为，多个关联参数优先使用已有领域对象、dataclass 或明确的数据结构。
- 纯查询与写操作必须分离：selector 不写数据库，service 不把请求对象当作隐式业务上下文；产生外部副作用的函数应在名称、文档或调用位置明确体现。
- 不使用可变对象作为默认参数；时间、随机值、外部客户端等不稳定依赖应在边界处获取或显式注入，以便测试。

### 类型注解

- 所有新增或修改的 Python 函数、方法都必须标注参数类型和返回类型，包括私有 helper；无返回值显式标注 `-> None`。覆写框架方法时保持与父类签名兼容。
- 类属性、模块级容器、空集合以及无法从赋值清晰推断的局部变量必须标注类型；简单局部变量无需重复标注。
- 优先使用 Python 3.13 原生类型语法，如 `list[str]`、`dict[str, int]`、`X | None`；仅在确有动态边界时使用 `Any`，并尽快在 serializer、schema、TypedDict、Protocol 或领域类型处收窄。
- Django 代码使用准确的框架类型，如 `HttpRequest`、DRF `Request`/`Response`、`QuerySet[Model]` 和具体模型类型；不得仅为消除类型错误而滥用 `cast()`、`# type: ignore` 或扩大为 `Any`。
- `# type: ignore[code]` 必须包含具体错误码，并附简短中文原因；能够通过正确建模、空值判断或类型守卫解决时不得忽略。

### 错误处理

- 只捕获能够恢复、转换或补充上下文的具体异常；禁止无差别捕获 `Exception` 后静默、返回成功或统一改成 400。
- API 的预期业务错误使用 DRF `ValidationError`、`PermissionDenied`、`NotFound` 或项目已有异常，并保持 `message/errors` 响应契约；不得向客户端暴露堆栈、SQL、文件路径或内部实现。
- 异常信息应说明失败的操作和非敏感标识；可恢复的依赖故障记录 `warning` 并按既有方案降级，不可恢复异常使用 `logger.exception()` 保留堆栈。
- 清理资源优先使用上下文管理器或 `finally`；事务内异常应继续冒泡以触发回滚，数据库提交后的通知、文件和缓存副作用使用 `transaction.on_commit()`。

### 数据模型与边界

- 外部输入一律视为不可信：HTTP/WebSocket/Celery 参数先在 serializer、form 或专用边界对象中完成类型、范围、枚举和跨字段校验，再进入 service。
- 业务不变量优先由数据库约束、模型约束和 service 共同保护；仅调用 `full_clean()` 不能替代 `UniqueConstraint`、`CheckConstraint`、事务或并发锁。
- 金额使用 `Decimal`/`DecimalField`，时间使用 Django 时区工具并保持 timezone-aware；状态值使用 `TextChoices` 或已有枚举，禁止散落魔法字符串。
- QuerySet 应在 selector 中统一处理可见性、稳定排序和关联预取；请求参数不得直接拼接到 raw SQL、`order_by()`、字段名或缓存键中。
- 跨模型写入使用 `transaction.atomic()`；竞争资源按固定顺序使用 `select_for_update()`，外部网络调用和耗时任务不应占用数据库事务。
- 修改模型字段、约束或索引时必须生成并审查 migration，评估现有数据兼容性、锁表风险、回滚路径及前后端/API 消费方。

### 测试

- 新增或修改行为必须同步测试；修复缺陷时先添加能稳定复现问题的回归测试，测试应验证公开行为而不是内部实现细节。
- 每个功能至少覆盖成功路径、关键边界、非法输入、权限和错误路径；涉及状态流转、并发、事务回滚、幂等或缓存降级时增加对应测试。
- 测试名称和中文 docstring 应表达“场景 + 预期结果”；遵循 Arrange-Act-Assert，单个测试聚焦一个行为，避免依赖执行顺序和共享可变状态。
- 优先使用 pytest fixture 和真实 ORM 行为；仅 mock 网络、时间、随机性等系统边界，不 mock 被测核心业务，也不以降低断言强度换取通过。
- API 测试同时断言状态码、关键响应结构、数据库状态和必要副作用；查询性能要求使用 `django_assert_num_queries` 固化，不能只断言返回 200。

### 工具链与自动检查

- Python 版本和依赖以 `pyproject.toml`、`uv.lock` 为唯一依据，统一使用 `uv` 执行命令；禁止手工修改锁文件或混用未记录的全局环境依赖。
- 提交前至少运行受影响 app 的 pytest 和 `uv run python backend/manage.py check`；模型变更额外运行 `makemigrations --check --dry-run` 并验证 migration，跨层变更同时执行前端 lint/build。
- Ruff、类型检查器或覆盖率工具一旦写入 `pyproject.toml` 和开发依赖，即成为强制质量门禁；新增代码不得通过关闭规则、整文件 ignore 或降低阈值规避失败。
- 当前未配置的工具不得在结果中声称已通过；若类型检查暂不可自动执行，代码审查仍必须逐项检查新增/修改函数的注解完整性，并在验证结果中明确说明限制。
- 自动生成 migration 后必须人工审查；格式化、lint、类型检查和测试只修改或验证当前任务范围，不能顺带重写无关文件。

### 文档与注释风格

- 模块、公共类、公共函数以及包含非显然业务规则的内部函数使用简洁中文 docstring，说明职责、关键约束或副作用，不重复翻译函数签名。
- docstring 使用一致的陈述风格；参数和返回值已能由名称与类型表达时不机械罗列，异常、幂等、事务、权限和外部副作用等重要契约必须写明。
- 行内注释解释“为什么”和业务限制，不解释显而易见的语法；注释必须随代码更新，过期注释视为缺陷。
- 面向用户的错误消息、项目文档和测试场景优先使用中文；类名、字段名、API 参数、协议名及第三方技术术语保留准确英文。
- 对外 API、环境变量、管理命令或部署行为发生变化时，同步更新 README、接口文档、示例配置和相关 Trellis spec，不仅修改代码。

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
- Git 提交流程继续遵循 `.trellis/workflow.md`。业务代码提交完成后，任务归档与 session journal 可以合并为一次 bookkeeping 提交，也可以选择遵循 `.trellis/workflow.md`；无论采用哪种方式，都应在提交计划中明确说明。其中每次提交均需获得用户确认。
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

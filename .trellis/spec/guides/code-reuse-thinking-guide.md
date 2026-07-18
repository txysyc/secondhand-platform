# 代码复用思维指南

## 先搜索再新增

在修改任何常量、状态、错误消息或配置前，先用 `rg` 搜索定义和消费者：

```powershell
rg -n "目标名称|目标字符串" backend frontend
```

优先复用现有边界：

- 列表查询复用 `catalog/selectors.py`、`orders/selectors.py` 等 selector。
- 写入和状态流转复用 `services.py`；分页和异常包装复用 `api/mixins.py`、`api/exceptions.py`。
- 缓存通过 `catalog/cache.py`、`messaging/selectors.py` 的键和失效函数访问，不在视图里拼 Redis key。
- API 与 WebSocket 需要相同载荷时复用 serializer 或 service 序列化函数，如 `messaging/services.py:serialize_private_message`。

## 何时抽象

出现以下任一情况时应提取共享函数/常量：同一业务规则出现三次以上、重复逻辑涉及权限/事务/状态机、或者多个消费者读取同一字段。不要为了一个简单的一次性表达式创建层级过深的工具模块。

特别是商品和订单状态：禁止在多个 view 中各自实现状态转换；扩展 `orders/services.py` 或 `catalog/services.py` 的白名单动作，并为每个分支补测试。

## 反重复清单

- 不复制 `message/errors` 错误包装、JWT 刷新、分页边界和对象权限检查。
- 不在多个 serializer/view 中重复同一字段组合校验；让 serializer 或 service 成为唯一规则所有者。
- 不让每个 WebSocket/HTTP 消费者分别解析同一消息载荷；统一使用 `serialize_private_message`。
- 新增字段后检查 Django serializer、前端 `types/`、endpoint 和页面的所有读写方。

## 提交前复查

确认新代码是否真正复用了已有实现，是否留下了重复常量或分叉状态机；批量修改后再次 `rg` 搜索旧名称和旧路径。

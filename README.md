# secondhand-platform

一个基于 Django 的二手交易平台项目，面向二手商品发布、浏览、购买、订单流转、评论互动和站内消息等基础交易场景。

## 功能概览

- 用户：注册、登录、个人资料、公开主页
- 商品：商品发布、列表浏览、详情查看、编辑与删除
- 订单：购买确认、买家订单、卖家订单、订单状态流转
- 互动：商品评论与回复
- 消息：会话列表、会话详情，基于 Channels 支持实时通信能力
- 后台：Django Admin 管理入口

## 技术栈

- Python 3.13+
- Django 6
- Django Channels / Daphne
- PostgreSQL
- Redis：缓存、Channels、Celery
- Celery：订单超时取消、自动签收、自动完成等异步任务
- uv：依赖与锁文件管理

## 快速开始

安装依赖：

```bash
uv sync
```

准备 `.env` 配置。项目会从仓库根目录读取 `.env`，可参考 `.env.example` 填写本地数据库、Redis 和 Django 配置。

执行迁移并启动开发服务：

```bash
cd secondhand-platform
uv run python manage.py migrate
uv run python manage.py runserver
```

访问地址：

- 首页：http://127.0.0.1:8000/
- 后台：http://127.0.0.1:8000/admin/

如需运行异步任务，可另开终端启动 Celery：

```bash
cd secondhand-platform
uv run celery -A config worker -l info
uv run celery -A config beat -l info
```

## 目录说明

```text
secondhand-platform/
  catalog/       商品模块
  users/         用户与资料模块
  orders/        订单模块
  interactions/  评论互动模块
  messaging/     站内消息模块
  config/        Django、ASGI、Celery 配置
  templates/     页面模板
  static/        静态资源
```

## 说明

当前项目处于开发阶段，还在不断完善中。

from django.apps import AppConfig


class UsersConfig(AppConfig):
    """users 应用配置。"""

    name = "users"

    def ready(self):
        """应用启动时注册 users 相关信号。

        Django 会在应用注册完成后调用该方法。这里导入 signals 模块，
        使 `post_save` 接收器完成注册。

        Returns:
            None: 该钩子只执行注册副作用，不返回业务数据。
        """

        from . import signals

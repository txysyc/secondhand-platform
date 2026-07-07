from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = 'catalog'

    def ready(self):
        """注册 catalog 缓存失效信号。"""

        from . import signals

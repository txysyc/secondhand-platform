"""secondhand-platform 的 Django 基础配置。"""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

# 构建项目内路径，例如 BASE_DIR / "subdir"。
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 读取环境变量
env = environ.Env()
environ.Env.read_env(BASE_DIR.parent / ".env")

# 开发期基础配置；生产发布前需要配合部署检查表逐项收紧。


ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")


# 应用注册

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "users.apps.UsersConfig",
    "catalog.apps.CatalogConfig",
    "orders.apps.OrdersConfig",
    "interactions.apps.InteractionsConfig",
    "messaging.apps.MessagingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # WhiteNoise 用于在 Django 进程中托管静态文件。
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# 数据库配置

DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE"),
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
    }
}


# 密码强度校验

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# 国际化与时区

LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE")

TIME_ZONE = env("DJANGO_TIME_ZONE")

USE_I18N = True

USE_TZ = True


# 静态文件与媒体文件

STATIC_URL = env("DJANGO_STATIC_URL")
STATIC_ROOT = BASE_DIR / str(env("DJANGO_STATIC_ROOT"))

MEDIA_URL = env("DJANGO_MEDIA_URL")
MEDIA_ROOT = BASE_DIR / str(env("DJANGO_MEDIA_ROOT"))

# 使用 users.User 作为全项目唯一用户模型，必须在首次迁移前确定。
AUTH_USER_MODEL = "users.User"

# 默认后端保留用户名认证与权限能力，邮箱后端只补充“邮箱 + 密码”登录入口。
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "users.auth_backends.EmailBackend",
]

# Redis-backed Django cache 与 Channels channel layer 使用独立 Redis DB。
# 本地默认连接 secondhand-platform-redis 容器映射到宿主机的 6380 端口。
DJANGO_CACHE_URL = env("DJANGO_CACHE_URL", default="redis://localhost:6380/2")
CHANNEL_REDIS_URL = env("CHANNEL_REDIS_URL", default="redis://localhost:6380/3")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": DJANGO_CACHE_URL,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [CHANNEL_REDIS_URL],
        },
    },
}

# DRF API 基础配置；业务阶段只在各 app 中补充 serializer、view 和权限。
REST_FRAMEWORK = {
    # 默认认证
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # 默认权限
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # 默认过滤后端
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    # 默认分页类
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    # 默认全局每页大小
    "PAGE_SIZE": 20,
    # 默认全局接口返回数据格式
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    # 默认异常处理器
    "EXCEPTION_HANDLER": "config.api_exceptions.api_exception_handler",
}

# JWT设置
SIMPLE_JWT = {
    # access_token过期时间
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    # refresh_token过期时间
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # jwt的http header类型
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# 开发期允许 Vite 前端访问 API；生产环境可通过环境变量覆盖。
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"]
)

# 默认主键类型

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery 通用配置

# Celery定时任务配置
CELERY_BEAT_SCHEDULE = {
    "cleanup_expired_unpaid_orders": {
        "task": "orders.tasks.cancel_expired_pending_orders_task",
        "schedule": crontab(minute="*/1"),
    },
    "mark_due_physical_orders_signed": {
        "task": "orders.tasks.mark_due_physical_orders_signed_task",
        "schedule": crontab(minute="*/10"),
    },
    "auto_complete_eligible_orders": {
        "task": "orders.tasks.auto_complete_eligible_orders_task",
        "schedule": crontab(minute="*/10"),
    },
}

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_ENABLE_UTC = True

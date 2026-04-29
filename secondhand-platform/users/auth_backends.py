"""自定义认证后端。"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailBackend(ModelBackend):
    """支持使用邮箱登录的认证后端。

    该后端只处理邮箱登录；用户名登录继续由 Django 默认 `ModelBackend`
    处理，以保留后台和权限系统的默认行为。
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """根据邮箱和密码认证用户。

        Args:
            request: 当前请求对象，保持与 Django 认证后端接口一致。
            username: 登录表单中的账号输入；在本后端中按邮箱处理。
            password: 登录表单中的明文密码。
            **kwargs: Django 认证系统传入的额外参数。

        Returns:
            User | None: 认证成功时返回用户对象；失败时返回 None。
        """

        email = username

        if email is None or password is None:
            return None

        email = email.strip()
        if email == "":
            return None

        # 邮箱登录必须大小写不敏感；如果出现大小写重复数据，拒绝认证以避免登录目标不确定。
        try:
            user = User.objects.get(email__iexact=email)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None

    def get_user(self, user_id):
        """根据用户主键读取用户对象。

        Args:
            user_id: Django session 中保存的用户主键。

        Returns:
            User | None: 找到用户时返回用户对象，否则返回 None。
        """

        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def user_can_authenticate(self, user):
        """判断用户是否允许登录。

        Args:
            user: 待认证的用户对象。

        Returns:
            bool: 用户未被禁用时返回 True。
        """

        return getattr(user, "is_active", True)

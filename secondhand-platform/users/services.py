"""用户注册相关服务。"""

from django.db import transaction
from django.contrib.auth.models import Group

from users.models import User


@transaction.atomic
def register_user(*, username, email, password):
    """创建用户并加入默认普通用户组。

    Args:
        username: 用户名。
        email: 已完成规范化的邮箱。
        password: 明文密码，由 Django 用户管理器负责哈希。

    Returns:
        User: 新创建并已加入默认用户组的用户对象。

    Raises:
        Group.DoesNotExist: 数据库中不存在名为“普通用户组”的前置用户组。
    """

    user = User.objects.create_user(username=username, email=email, password=password)

    group = Group.objects.get(name="普通用户组")
    user.groups.add(group)

    return user


@transaction.atomic
def register_add_group(form):
    """兼容旧模板表单的注册入口，内部复用表单无关服务。"""

    return register_user(
        username=form.cleaned_data["username"],
        email=form.cleaned_data["email"],
        password=form.cleaned_data["password1"],
    )

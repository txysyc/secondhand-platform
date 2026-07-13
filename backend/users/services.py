"""用户领域服务。"""

from django.contrib.auth.models import Group
from django.db import transaction

from users.models import User, UserAddress


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
def create_user_address(*, user, data):
    """创建用户地址，并在需要时切换默认地址。

    锁定用户记录，避免同一用户并发创建默认地址时破坏唯一约束。
    """
    lock_user = User.objects.select_for_update().get(pk=user.pk)
    should_set_default = data.get("is_default", False)

    if should_set_default:
        UserAddress.objects.filter(user=lock_user, is_default=True).update(
            is_default=False
        )

    address_data = {**data, "is_default": should_set_default}
    return UserAddress.objects.create(user=lock_user, **address_data)

"""用户注册相关服务。"""

from django.db import transaction
from django.contrib.auth.models import Group


@transaction.atomic
def register_add_group(form):
    """保存注册用户并加入默认普通用户组。

    Args:
        form: 已通过校验的注册表单，必须提供 `save()` 方法并返回用户对象。

    Returns:
        User: 新创建并已加入默认用户组的用户对象。

    Raises:
        Group.DoesNotExist: 数据库中不存在名为“普通用户组”的前置用户组。
    """

    user = form.save()

    group = Group.objects.get(name="普通用户组")
    user.groups.add(group)

    return user

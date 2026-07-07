from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, Profile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, raw, **kwargs):
    """用户创建后自动补建资料。

    raw=True 通常来自 fixture 加载，此时跳过自动创建，避免导入历史数据时产生额外写入。

    Args:
        sender (type[User]): 发送 `post_save` 信号的模型类。
        instance (User): 本次保存的用户实例。
        created (bool): 是否为新创建的用户记录。
        raw (bool): 是否为原始数据加载流程触发的保存。
        **kwargs: Django 信号框架传入的其他上下文参数。

    Returns:
        None: 该处理器只维护 Profile 创建副作用。
    """

    if raw:
        return

    if not created:
        return

    profile, _ = Profile.objects.get_or_create(user=instance)

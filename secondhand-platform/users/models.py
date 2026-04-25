from uuid import uuid4
from pathlib import Path

from django.conf import settings
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinLengthValidator


class User(AbstractUser):
    """平台自定义用户模型。

    在 Django 默认用户模型基础上收紧用户名长度，并要求邮箱唯一。
    该模型通过 `AUTH_USER_MODEL` 作为全项目唯一用户模型使用。
    """

    username = models.CharField(
        verbose_name="用户名",
        max_length=6,
        validators=[MinLengthValidator(2, message="用户名长度不得少于2位")],
        unique=True,
    )
    email = models.EmailField(
        verbose_name="用户邮箱", unique=True, null=False, blank=False
    )

    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    def __str__(self):
        """返回后台和调试场景中展示的用户账号名称。

        Returns:
            str: 包含用户名的账号展示文本。
        """

        return f"{self.username}的账号"


def avatar_upload_to(instance, filename):
    """生成用户头像上传路径。

    使用用户 ID 作为目录，使用 UUID 作为文件名，避免不同用户或同一用户
    多次上传时发生文件名冲突。原始文件无扩展名时默认使用 `.jpg`。

    Args:
        instance (Profile): 正在保存头像的用户资料实例。
        filename (str): 用户上传文件的原始文件名。

    Returns:
        str: 头像文件相对于 MEDIA_ROOT 的存储路径。
    """

    ext = Path(filename).suffix.lower() or ".jpg"
    return f"avatars/users/{instance.user_id}/{uuid4().hex}{ext}"


class Profile(models.Model):
    """用户资料模型。

    保存用户昵称、头像和简介等扩展信息。每个用户最多拥有一份资料，
    用户删除时资料会通过级联删除一并清理。
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="用户",
    )
    nickname = models.CharField(
        verbose_name="用户昵称",
        max_length=10,
        validators=[MinLengthValidator(1, message="用户昵称长度不能为空")],
        null=True,
        blank=True,
    )
    avatar = models.ImageField(
        verbose_name="用户头像",
        upload_to=avatar_upload_to,
        blank=True,
        null=True,
    )
    bio = models.TextField(verbose_name="简介", null=True, blank=True)
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    def __str__(self):
        """返回后台和调试场景中展示的用户资料名称。

        Returns:
            str: 包含用户名的用户资料展示文本。
        """

        return f"{self.user.username}的用户资料"

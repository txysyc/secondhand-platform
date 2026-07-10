"""站内通知 API 序列化器。"""

from rest_framework import serializers

from notifications.models import Notification
from users.models import Profile, User


class NotificationProfileSerializer(serializers.ModelSerializer):
    """通知中展示的用户资料摘要。"""

    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["nickname", "avatar", "avatar_url", "bio"]

    def get_avatar_url(self, obj):
        """返回头像可访问地址。"""

        if not obj or not obj.avatar:
            return None
        return obj.avatar.url


class NotificationActorSerializer(serializers.ModelSerializer):
    """通知触发用户摘要，避免携带公开主页商品列表。"""

    profile = NotificationProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "profile"]


class NotificationSerializer(serializers.ModelSerializer):
    """站内通知响应。"""

    actor = NotificationActorSerializer(read_only=True)
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "title",
            "content",
            "actor",
            "target_type",
            "target_id",
            "target_url",
            "payload",
            "is_read",
            "read_at",
            "created_at",
        ]

    def get_is_read(self, obj):
        """返回通知是否已读。"""

        return obj.read_at is not None

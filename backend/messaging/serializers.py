"""私信 API 序列化器。"""

from rest_framework import serializers

from messaging.models import Conversation, PrivateMessage
from messaging.services import MAX_PRIVATE_MESSAGE_LENGTH
from users.serializers import ProfileSerializer
from users.models import User


class MessagingUserSerializer(serializers.ModelSerializer):
    """私信参与者用户摘要。"""

    profile = ProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "profile"]


class ConversationSerializer(serializers.ModelSerializer):
    """会话列表和详情响应。"""

    participant_a = MessagingUserSerializer(read_only=True)
    participant_b = MessagingUserSerializer(read_only=True)
    other_participant = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True, default=0)
    latest_message_content = serializers.CharField(
        read_only=True,
        allow_null=True,
        default=None,
    )
    latest_message_created_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        default=None,
    )

    class Meta:
        model = Conversation
        fields = [
            "id",
            "participant_a",
            "participant_b",
            "other_participant",
            "unread_count",
            "latest_message_content",
            "latest_message_created_at",
            "created_at",
            "updated_at",
        ]

    def get_other_participant(self, obj):
        request = self.context.get("request")
        other_user = obj.other_participant(getattr(request, "user", None))
        if other_user is None:
            return None
        return MessagingUserSerializer(other_user).data


class ConversationCreateSerializer(serializers.Serializer):
    """发起或复用会话请求。"""

    target_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        source="target_user",
    )


class PrivateMessageSerializer(serializers.ModelSerializer):
    """私信消息响应。"""

    conversation_id = serializers.IntegerField(read_only=True)
    sender = MessagingUserSerializer(read_only=True)

    class Meta:
        model = PrivateMessage
        fields = [
            "id",
            "conversation_id",
            "sender",
            "content",
            "read_at",
            "created_at",
        ]


class PrivateMessageCreateSerializer(serializers.Serializer):
    """发送私信请求。"""

    content = serializers.CharField(
        max_length=MAX_PRIVATE_MESSAGE_LENGTH,
        trim_whitespace=True,
        allow_blank=True,
        error_messages={
            "blank": "消息内容不能为空",
            "max_length": f"消息内容不能超过 {MAX_PRIVATE_MESSAGE_LENGTH} 个字符",
        },
    )

    def validate_content(self, value):
        if value == "":
            raise serializers.ValidationError("消息内容不能为空")
        return value


from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from messaging.models import Conversation, PrivateMessage

MAX_PRIVATE_MESSAGE_LENGTH = 1000


def get_or_create_conversation(user, target_user):
    """获取或创建两个登录用户之间的一对一会话。"""

    _ensure_authenticated(user)
    if target_user is None or not target_user.is_active:
        raise ValidationError("目标用户不可用")
    if user.pk == target_user.pk:
        raise ValidationError("不能给自己发送私信")

    participant_a, participant_b = sorted([user, target_user], key=lambda item: item.pk)
    conversation, _ = Conversation.objects.get_or_create(
        participant_a=participant_a,
        participant_b=participant_b,
    )
    return conversation


def create_private_message(user, conversation, content):
    """在会话中创建一条私信，并刷新会话更新时间。"""

    _ensure_authenticated(user)
    _ensure_conversation_participant(user, conversation)
    content = _clean_private_message_content(content)

    with transaction.atomic():
        locked_conversation = Conversation.objects.select_for_update().get(
            pk=conversation.pk
        )
        _ensure_conversation_participant(user, locked_conversation)
        message = PrivateMessage.objects.create(
            conversation=locked_conversation,
            sender=user,
            content=content,
        )
        locked_conversation.save(update_fields=["updated_at"])
    return message


def mark_conversation_read(user, conversation):
    """把当前用户收到的未读消息标记为已读。"""

    _ensure_authenticated(user)
    _ensure_conversation_participant(user, conversation)
    return (
        conversation.private_messages.filter(read_at__isnull=True)
        .exclude(sender=user)
        .update(read_at=timezone.now())
    )


def serialize_private_message(message):
    """生成 WebSocket 广播使用的安全消息载荷。"""

    sender = message.sender
    profile = getattr(sender, "profile", None)
    sender_display_name = getattr(profile, "nickname", "") or sender.username
    return {
        "id": message.pk,
        "conversation_id": message.conversation_id,
        "sender_id": sender.pk,
        "sender_display_name": sender_display_name,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }


def _ensure_authenticated(user):
    if user is None or not user.is_authenticated:
        raise PermissionDenied("请先登录后再使用私信")


def _ensure_conversation_participant(user, conversation):
    if not conversation.has_participant(user):
        raise PermissionDenied("无权访问该私信会话")


def _clean_private_message_content(content):
    content = (content or "").strip()
    if content == "":
        raise ValidationError("消息内容不能为空")
    if len(content) > MAX_PRIVATE_MESSAGE_LENGTH:
        raise ValidationError(f"消息内容不能超过 {MAX_PRIVATE_MESSAGE_LENGTH} 个字符")
    return content


def get_user_by_id(user_id):
    """供异步 Consumer 使用的用户读取入口。"""

    return get_user_model().objects.get(pk=user_id)

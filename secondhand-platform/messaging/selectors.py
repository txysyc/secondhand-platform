from django.core.exceptions import PermissionDenied
from django.db.models import Count, OuterRef, Q, Subquery

from messaging.models import Conversation, PrivateMessage


def get_user_conversations(user):
    """读取用户参与的会话列表，并附带未读数与最近消息摘要。"""

    if user is None or not user.is_authenticated:
        return Conversation.objects.none()
    latest_messages = PrivateMessage.objects.filter(conversation=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    return (
        Conversation.objects.filter(Q(participant_a=user) | Q(participant_b=user))
        .select_related(
            "participant_a",
            "participant_a__profile",
            "participant_b",
            "participant_b__profile",
        )
        .annotate(
            unread_count=Count(
                "private_messages",
                filter=Q(private_messages__read_at__isnull=True)
                & ~Q(private_messages__sender_id=user.pk),
            ),
            latest_message_content=Subquery(latest_messages.values("content")[:1]),
            latest_message_created_at=Subquery(
                latest_messages.values("created_at")[:1]
            ),
        )
        .order_by("-updated_at", "-id")
    )


def get_conversation_for_user(user, conversation_id):
    """读取当前用户可访问的单个会话。"""

    if user is None or not user.is_authenticated:
        raise PermissionDenied("请先登录后再使用私信")
    return get_user_conversations(user).get(pk=conversation_id)


def get_conversation_messages(conversation):
    """读取会话内按时间顺序展示的消息列表。"""

    return (
        PrivateMessage.objects.filter(conversation=conversation)
        .select_related("sender", "sender__profile")
        .order_by("created_at", "id")
    )

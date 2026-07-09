from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, OuterRef, Q, Subquery
from rest_framework.exceptions import PermissionDenied

from messaging.models import Conversation, PrivateMessage

DEFAULT_MESSAGE_WINDOW_SIZE = 20
MAX_MESSAGE_WINDOW_SIZE = 100


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


def get_conversation_message_window(
    conversation,
    *,
    before_id=None,
    after_id=None,
    latest=False,
    limit=DEFAULT_MESSAGE_WINDOW_SIZE,
):
    """读取聊天窗口需要的一段消息，避免每次进入或收发后重新加载完整历史。"""

    if before_id and after_id:
        raise ValueError("before_id 与 after_id 不能同时使用")

    limit = _normalize_message_window_limit(limit)
    if after_id:
        return list(_base_message_queryset(conversation).filter(id__gt=after_id)[:limit])

    if before_id:
        return _previous_message_window(conversation, before_id, limit)

    if latest:
        return _cached_latest_message_window(conversation, limit)

    return list(_base_message_queryset(conversation)[:limit])


def get_conversation_message_cursor_page(
    conversation,
    *,
    before_id=None,
    after_id=None,
    latest=False,
    limit=DEFAULT_MESSAGE_WINDOW_SIZE,
):
    """读取一页游标消息，并返回前后游标元信息。"""

    messages = get_conversation_message_window(
        conversation,
        before_id=before_id,
        after_id=after_id,
        latest=latest,
        limit=limit,
    )
    normalized_limit = _normalize_message_window_limit(limit)
    first_id = messages[0].id if messages else None
    last_id = messages[-1].id if messages else None

    return {
        "results": messages,
        "before_cursor": first_id,
        "after_cursor": last_id,
        "has_more_before": _has_message_before(conversation, first_id),
        "has_more_after": _has_message_after(conversation, last_id),
        "page_size": normalized_limit,
    }


def invalidate_conversation_message_cache(conversation_id):
    """清理会话最新消息窗口缓存，供新消息写入后调用。"""

    cache.delete(_latest_message_window_cache_key(conversation_id))


def _base_message_queryset(conversation):
    """构造消息基础查询，统一预取发送者资料并按展示顺序排序。"""

    return (
        PrivateMessage.objects.filter(conversation=conversation)
        .select_related("sender", "sender__profile")
        .order_by("created_at", "id")
    )


def _previous_message_window(conversation, before_id, limit):
    """读取指定消息之前的一屏历史，并恢复为聊天展示需要的正序。"""

    messages = list(
        PrivateMessage.objects.filter(conversation=conversation, id__lt=before_id)
        .select_related("sender", "sender__profile")
        .order_by("-created_at", "-id")[:limit]
    )
    return list(reversed(messages))


def _cached_latest_message_window(conversation, limit):
    """读取最新一屏消息；默认大小时使用 Redis/Django cache 降低重复进入成本。"""

    if limit != DEFAULT_MESSAGE_WINDOW_SIZE:
        return _latest_message_window(conversation, limit)

    cache_key = _latest_message_window_cache_key(conversation.pk)
    message_ids = cache.get(cache_key)
    if message_ids is None:
        messages = _latest_message_window(conversation, limit)
        cache.set(
            cache_key,
            [message.pk for message in messages],
            getattr(settings, "PRIVATE_MESSAGE_LATEST_CACHE_TIMEOUT", 30),
        )
        return messages

    messages_by_id = {
        message.pk: message
        for message in _base_message_queryset(conversation).filter(id__in=message_ids)
    }
    return [messages_by_id[message_id] for message_id in message_ids if message_id in messages_by_id]


def _latest_message_window(conversation, limit):
    """读取会话最新一屏消息，并恢复为正序展示。"""

    messages = list(
        PrivateMessage.objects.filter(conversation=conversation)
        .select_related("sender", "sender__profile")
        .order_by("-created_at", "-id")[:limit]
    )
    return list(reversed(messages))


def _has_message_before(conversation, message_id):
    """判断指定消息之前是否还有更早历史。"""

    if message_id is None:
        return False
    return PrivateMessage.objects.filter(
        conversation=conversation,
        id__lt=message_id,
    ).exists()


def _has_message_after(conversation, message_id):
    """判断指定消息之后是否还有更新消息。"""

    if message_id is None:
        return False
    return PrivateMessage.objects.filter(
        conversation=conversation,
        id__gt=message_id,
    ).exists()


def _latest_message_window_cache_key(conversation_id):
    """生成会话最新消息窗口缓存键。"""

    return f"messaging:conversation:{conversation_id}:messages:latest"


def _normalize_message_window_limit(limit):
    """限制单次窗口读取大小，避免前端误传过大 limit 导致接口退化为全量加载。"""

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_MESSAGE_WINDOW_SIZE
    return min(max(limit, 1), MAX_MESSAGE_WINDOW_SIZE)

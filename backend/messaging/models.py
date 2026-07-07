from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Conversation(models.Model):
    """两个用户之间唯一的一对一私信会话。

    会话参与者按用户 ID 从小到大固定写入 participant_a 和 participant_b，
    避免 A-B 与 B-A 在数据库中形成两条重复会话。
    """

    # 会话双方使用两个独立外键存储，便于建立唯一约束和按参与者查询会话列表。
    participant_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_a",
        verbose_name="参与者 A",
    )
    participant_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_b",
        verbose_name="参与者 B",
    )
    # updated_at 会在新消息写入时由服务层主动刷新，用作最近会话排序依据。
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    class Meta:
        verbose_name = "私信会话"
        verbose_name_plural = "私信会话"
        ordering = ["-updated_at", "-id"]
        indexes = [
            # 分别覆盖当前用户作为 participant_a 或 participant_b 时的最近会话查询。
            models.Index(fields=["participant_a", "-updated_at"]),
            models.Index(fields=["participant_b", "-updated_at"]),
        ]
        constraints = [
            # 同一对参与者只能有一条会话记录。
            models.UniqueConstraint(
                fields=["participant_a", "participant_b"],
                name="messaging_unique_conversation_pair",
            ),
            # 强制参与者按 ID 升序保存，同时防止用户和自己创建会话。
            models.CheckConstraint(
                condition=Q(participant_a_id__lt=F("participant_b_id")),
                name="messaging_ordered_participants",
            ),
        ]

    def __str__(self):
        """返回后台管理和调试输出中使用的会话描述。"""

        return f"{self.participant_a} 与 {self.participant_b} 的会话"

    def has_participant(self, user):
        """判断给定用户是否是当前会话参与者。"""

        return (
            user is not None
            and user.is_authenticated
            and user.pk in {self.participant_a_id, self.participant_b_id}
        )

    def other_participant(self, user):
        """返回当前会话中除给定用户以外的另一位参与者。"""

        if user.pk == self.participant_a_id:
            return self.participant_b
        if user.pk == self.participant_b_id:
            return self.participant_a
        return None


class PrivateMessage(models.Model):
    """会话中的单条私信。

    消息只记录发送者，接收者可通过所属会话和发送者反推出；
    read_at 为空表示接收方尚未读取。
    """

    # 删除会话时级联删除消息，保证不会留下脱离会话的私信记录。
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="private_messages",
        verbose_name="所属会话",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_private_messages",
        verbose_name="发送者",
    )
    # 内容长度同时由 API 入参和服务层校验；模型层保留上限作为最终约束。
    content = models.TextField(verbose_name="内容", max_length=1000)
    read_at = models.DateTimeField(verbose_name="读取时间", null=True, blank=True)
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "私信"
        verbose_name_plural = "私信"
        ordering = ["created_at", "id"]
        indexes = [
            # 会话详情 API 按时间顺序读取消息。
            models.Index(fields=["conversation", "created_at", "id"]),
            # 后台或统计场景按发送者查询消息。
            models.Index(fields=["sender", "created_at"]),
        ]

    def __str__(self):
        """返回消息内容摘要，避免后台列表直接展示完整长文本。"""

        return self.content[:20]

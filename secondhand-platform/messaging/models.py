from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Conversation(models.Model):
    """两个用户之间唯一的一对一私信会话。"""

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
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    updated_at = models.DateTimeField(verbose_name="更新时间", auto_now=True)

    class Meta:
        verbose_name = "私信会话"
        verbose_name_plural = "私信会话"
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["participant_a", "-updated_at"]),
            models.Index(fields=["participant_b", "-updated_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["participant_a", "participant_b"],
                name="messaging_unique_conversation_pair",
            ),
            models.CheckConstraint(
                condition=Q(participant_a_id__lt=F("participant_b_id")),
                name="messaging_ordered_participants",
            ),
        ]

    def __str__(self):
        return f"{self.participant_a} 与 {self.participant_b} 的会话"

    def has_participant(self, user):
        return (
            user is not None
            and user.is_authenticated
            and user.pk in {self.participant_a_id, self.participant_b_id}
        )

    def other_participant(self, user):
        if user.pk == self.participant_a_id:
            return self.participant_b
        if user.pk == self.participant_b_id:
            return self.participant_a
        return None


class PrivateMessage(models.Model):
    """会话中的单条私信。"""

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
    content = models.TextField(verbose_name="内容", max_length=1000)
    read_at = models.DateTimeField(verbose_name="读取时间", null=True, blank=True)
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "私信"
        verbose_name_plural = "私信"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at", "id"]),
            models.Index(fields=["sender", "created_at"]),
        ]

    def __str__(self):
        return self.content[:20]

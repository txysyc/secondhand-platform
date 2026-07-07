from django.conf import settings

from django.db import models


class Comment(models.Model):
    """商品留言模型，支持一层回复结构。"""

    class Meta:
        verbose_name = "评论"
        verbose_name_plural = "评论"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["listing", "parent", "created_at", "id"],
                name="interaction_listing_parent_idx",
            )
        ]

    # 作者可为空：作者注销后，评论依旧存在
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comments",
        verbose_name="作者",
    )
    # 所属商品注销后，评论删除
    listing = models.ForeignKey(
        "catalog.Listing",
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="所属商品",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
        verbose_name="父留言",
    )
    content = models.TextField(max_length=1000, verbose_name="内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def __str__(self):
        """返回后台和调试输出中展示的留言摘要。"""

        n = 20
        return self.content[0:n]

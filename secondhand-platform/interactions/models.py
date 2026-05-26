from django.conf import settings

from django.db import models


# Create your models here.
class Comment(models.Model):
    class Meta:
        verbose_name = "评论"
        verbose_name_plural = "评论"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["listing", "created_at", "id"])]

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
    content = models.TextField(max_length=1000, verbose_name="内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def __str__(self):
        n = 20
        return self.content[0:n]

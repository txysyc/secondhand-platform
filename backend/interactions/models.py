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


class ListingFavorite(models.Model):
    """商品收藏模型，记录用户与商品之间的收藏关系。"""

    class Meta:
        verbose_name = "商品收藏"
        verbose_name_plural = "商品收藏"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "listing"],
                name="uniq_listing_favorite_user_listing",
            )
        ]
        indexes = [
            # 我的收藏列表按用户和收藏时间倒序读取。
            models.Index(
                fields=["user", "-created_at"],
                name="favorite_user_created_idx",
            ),
            # 后台按商品排查收藏数据时复用该索引。
            models.Index(
                fields=["listing", "-created_at"],
                name="favorite_listing_created_idx",
            ),
        ]

    # 用户注销后，收藏关系一并清理。
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listing_favorites",
        verbose_name="收藏用户",
    )
    # 商品删除后，相关收藏关系一并清理。
    listing = models.ForeignKey(
        "catalog.Listing",
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="收藏商品",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="收藏时间")

    def __str__(self):
        """返回后台和调试输出中展示的收藏关系。"""

        return f"{self.user} 收藏 {self.listing}"


class ListingViewHistory(models.Model):
    """商品浏览历史模型，记录用户最近访问商品的时间。"""

    class Meta:
        verbose_name = "浏览历史"
        verbose_name_plural = "浏览历史"
        ordering = ["-viewed_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "listing"],
                name="uniq_listing_view_user_listing",
            )
        ]
        indexes = [
            # 我的浏览历史列表按用户和最近浏览时间倒序读取。
            models.Index(
                fields=["user", "-viewed_at"],
                name="view_user_viewed_idx",
            ),
            # 后台按商品排查浏览数据时复用该索引。
            models.Index(
                fields=["listing", "-viewed_at"],
                name="view_listing_viewed_idx",
            ),
        ]

    # 用户注销后，浏览历史一并清理。
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listing_view_history",
        verbose_name="浏览用户",
    )
    # 商品删除后，相关浏览历史一并清理。
    listing = models.ForeignKey(
        "catalog.Listing",
        on_delete=models.CASCADE,
        related_name="view_history",
        verbose_name="浏览商品",
    )
    viewed_at = models.DateTimeField(auto_now=True, verbose_name="浏览时间")

    def __str__(self):
        """返回后台和调试输出中展示的浏览关系。"""

        return f"{self.user} 浏览 {self.listing}"

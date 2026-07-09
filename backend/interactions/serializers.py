"""interactions API 序列化器。"""

from rest_framework import serializers

from catalog.serializers import ListingDetailSerializer
from interactions.models import Comment
from interactions.models import ListingFavorite, ListingViewHistory
from users.models import Profile, User


class ProfileSummarySerializer(serializers.ModelSerializer):
    """评论作者资料摘要。"""

    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = ["nickname", "avatar", "avatar_url", "bio"]

    def get_avatar_url(self, obj):
        if not obj or not obj.avatar:
            return None
        return obj.avatar.url


class CommentAuthorSerializer(serializers.ModelSerializer):
    """评论作者摘要。"""

    profile = ProfileSummarySerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "profile"]


class CommentWriteSerializer(serializers.Serializer):
    """评论写入参数。"""

    content = serializers.CharField(
        max_length=1000,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate_content(self, value):
        content = value.strip()
        if not content:
            raise serializers.ValidationError("留言内容不能为空")
        return content


class CommentSerializer(serializers.ModelSerializer):
    """评论响应。"""

    author = CommentAuthorSerializer(read_only=True)
    replies = serializers.SerializerMethodField()
    parent_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Comment
        fields = [
            "id",
            "content",
            "created_at",
            "updated_at",
            "parent_id",
            "author",
            "replies",
        ]

    def get_replies(self, obj):
        replies = getattr(obj, "replies", None)
        if replies is None:
            return []
        queryset = replies.all()
        return CommentSerializer(queryset, many=True, context=self.context).data


class FavoriteStateSerializer(serializers.Serializer):
    """商品收藏操作响应。"""

    listing_id = serializers.IntegerField()
    is_favorited = serializers.BooleanField()


class ListingFavoriteSerializer(serializers.ModelSerializer):
    """我的收藏列表响应。"""

    listing = ListingDetailSerializer(read_only=True)

    class Meta:
        model = ListingFavorite
        fields = ["id", "created_at", "listing"]


class ListingViewHistorySerializer(serializers.ModelSerializer):
    """我的浏览历史列表响应。"""

    listing = ListingDetailSerializer(read_only=True)

    class Meta:
        model = ListingViewHistory
        fields = ["id", "viewed_at", "listing"]

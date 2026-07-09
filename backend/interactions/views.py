"""interactions 应用 API 类视图。"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import PageNumberPaginationMixin
from catalog.selectors import get_visible_listing_detail_queryset
from interactions.permissions import IsCommentAuthor
from interactions.serializers import (
    CommentSerializer,
    CommentWriteSerializer,
    FavoriteStateSerializer,
    ListingFavoriteSerializer,
    ListingViewHistorySerializer,
)
from interactions.models import Comment
from interactions.selectors import (
    get_listing_comments,
    get_user_favorite_items,
    get_user_view_history_items,
)
from interactions.services import (
    create_comment,
    create_reply,
    delete_comment,
    favorite_listing,
    unfavorite_listing,
)


class _VisibleListingMixin:
    """按当前用户可见性读取留言所属商品。"""

    def get_visible_listing_queryset(self, user):
        """构建评论接口可访问的商品范围。"""

        return get_visible_listing_detail_queryset(user)

    def get_visible_listing_or_404(self, request, listing_id):
        queryset = self.get_visible_listing_queryset(request.user)
        return get_object_or_404(queryset, pk=listing_id)

    def get_visible_comment_or_404(self, request, comment_id):
        """读取评论并复用商品可见性规则，避免通过评论 ID 绕过商品权限。"""

        comment = get_object_or_404(
            Comment.objects.select_related(
                "listing",
                "listing__category",
                "listing__owner",
                "listing__owner__profile",
                "author",
                "author__profile",
            ),
            pk=comment_id,
        )
        self.get_visible_listing_or_404(request, comment.listing_id)
        return comment


class ListingCommentApiView(_VisibleListingMixin, APIView):
    """商品评论列表和顶层评论创建。"""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request, listing_id):
        listing = self.get_visible_listing_or_404(request, listing_id)
        comments = get_listing_comments(listing)
        serializer = CommentSerializer(comments, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request, listing_id):
        listing = self.get_visible_listing_or_404(request, listing_id)
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = create_comment(
            request.user,
            listing,
            serializer.validated_data["content"],
        )
        response_serializer = CommentSerializer(comment, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CommentReplyApiView(_VisibleListingMixin, APIView):
    """评论回复创建。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, comment_id):
        parent_comment = self.get_visible_comment_or_404(request, comment_id)
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply = create_reply(
            request.user,
            parent_comment,
            serializer.validated_data["content"],
        )
        response_serializer = CommentSerializer(reply, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CommentDeleteApiView(_VisibleListingMixin, APIView):
    """删除自己的评论。"""

    permission_classes = [IsAuthenticated, IsCommentAuthor]

    def get_object(self, request, comment_id):
        comment = self.get_visible_comment_or_404(request, comment_id)
        self.check_object_permissions(request, comment)
        return comment

    def delete(self, request, comment_id):
        comment = self.get_object(request, comment_id)
        delete_comment(request.user, comment)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListingFavoriteApiView(_VisibleListingMixin, APIView):
    """商品收藏与取消收藏。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        listing = self.get_visible_listing_or_404(request, listing_id)
        favorite_listing(request.user, listing)
        serializer = FavoriteStateSerializer(
            {"listing_id": listing.id, "is_favorited": True}
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, listing_id):
        self.get_visible_listing_or_404(request, listing_id)
        unfavorite_listing(request.user, listing_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyFavoriteListApiView(PageNumberPaginationMixin, APIView):
    """当前用户的商品收藏列表。"""

    permission_classes = [IsAuthenticated]
    max_page_size = 50

    def get(self, request):
        queryset = get_user_favorite_items(request.user)
        return self.paginate(request, queryset, ListingFavoriteSerializer)


class MyViewHistoryListApiView(PageNumberPaginationMixin, APIView):
    """当前用户的浏览历史列表。"""

    permission_classes = [IsAuthenticated]
    max_page_size = 50

    def get(self, request):
        queryset = get_user_view_history_items(request.user)
        return self.paginate(request, queryset, ListingViewHistorySerializer)


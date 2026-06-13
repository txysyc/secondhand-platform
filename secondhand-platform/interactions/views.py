"""interactions 应用 API 类视图。"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.api_mixins import ServiceErrorMixin
from catalog.models import Listing
from interactions.permissions import IsCommentAuthor
from interactions.serializers import CommentSerializer, CommentWriteSerializer
from interactions.models import Comment
from interactions.selectors import get_listing_comments
from interactions.services import create_comment, create_reply, delete_comment


class _VisibleListingMixin:
    """按当前用户可见性读取留言所属商品。"""

    def get_visible_listing_queryset(self, user):
        """构建评论接口可访问的商品范围。"""

        public_filter = Q(
            status__in=[
                Listing.Status.ACTIVE,
                Listing.Status.RESERVED,
                Listing.Status.SOLD,
            ],
            category__is_active=True,
        )
        queryset = Listing.objects.select_related(
            "category",
            "owner",
            "owner__profile",
        ).prefetch_related("images")
        if user.is_authenticated:
            # 卖家仍可查看自己已下架商品下的历史评论，普通访客不可见。
            public_filter |= Q(owner=user, status=Listing.Status.WITHDRAWN)
        return queryset.filter(public_filter)

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


class ListingCommentApiView(ServiceErrorMixin, _VisibleListingMixin, APIView):
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
        comment = self.run_service(
            create_comment,
            request.user,
            listing,
            serializer.validated_data["content"],
        )
        response_serializer = CommentSerializer(comment, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CommentReplyApiView(ServiceErrorMixin, _VisibleListingMixin, APIView):
    """评论回复创建。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, comment_id):
        parent_comment = self.get_visible_comment_or_404(request, comment_id)
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply = self.run_service(
            create_reply,
            request.user,
            parent_comment,
            serializer.validated_data["content"],
        )
        response_serializer = CommentSerializer(reply, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CommentDeleteApiView(ServiceErrorMixin, _VisibleListingMixin, APIView):
    """删除自己的评论。"""

    permission_classes = [IsAuthenticated, IsCommentAuthor]

    def get_object(self, request, comment_id):
        comment = self.get_visible_comment_or_404(request, comment_id)
        self.check_object_permissions(request, comment)
        return comment

    def delete(self, request, comment_id):
        comment = self.get_object(request, comment_id)
        self.run_service(delete_comment, request.user, comment)
        return Response(status=status.HTTP_204_NO_CONTENT)


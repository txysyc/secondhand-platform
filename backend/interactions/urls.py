"""interactions 应用 API 路由。"""

from django.urls import path

from interactions.views import (
    CommentDeleteAPIView,
    CommentReplyAPIView,
    ListingCommentAPIView,
    ListingFavoriteAPIView,
    MyFavoriteListAPIView,
    MyViewHistoryListAPIView,
)

urlpatterns = [
    path(
        "listings/<int:listing_id>/comments/",
        ListingCommentAPIView.as_view(),
        name="listing_comments",
    ),
    path(
        "comments/<int:comment_id>/replies/",
        CommentReplyAPIView.as_view(),
        name="comment_replies",
    ),
    path(
        "comments/<int:comment_id>/",
        CommentDeleteAPIView.as_view(),
        name="comment_detail",
    ),
    path(
        "listings/<int:listing_id>/favorite/",
        ListingFavoriteAPIView.as_view(),
        name="listing_favorite",
    ),
    path(
        "my/favorites/",
        MyFavoriteListAPIView.as_view(),
        name="my_favorites",
    ),
    path(
        "my/browse-history/",
        MyViewHistoryListAPIView.as_view(),
        name="my_browse_history",
    ),
]


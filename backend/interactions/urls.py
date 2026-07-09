"""interactions 应用 API 路由。"""

from django.urls import path

from interactions.views import (
    CommentDeleteApiView,
    CommentReplyApiView,
    ListingCommentApiView,
    ListingFavoriteApiView,
    MyFavoriteListApiView,
    MyViewHistoryListApiView,
)

urlpatterns = [
    path(
        "listings/<int:listing_id>/comments/",
        ListingCommentApiView.as_view(),
        name="listing_comments",
    ),
    path(
        "comments/<int:comment_id>/replies/",
        CommentReplyApiView.as_view(),
        name="comment_replies",
    ),
    path(
        "comments/<int:comment_id>/",
        CommentDeleteApiView.as_view(),
        name="comment_detail",
    ),
    path(
        "listings/<int:listing_id>/favorite/",
        ListingFavoriteApiView.as_view(),
        name="listing_favorite",
    ),
    path(
        "my/favorites/",
        MyFavoriteListApiView.as_view(),
        name="my_favorites",
    ),
    path(
        "my/browse-history/",
        MyViewHistoryListApiView.as_view(),
        name="my_browse_history",
    ),
]


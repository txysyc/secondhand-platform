"""interactions 应用 API 路由。"""

from django.urls import path

from interactions.api.views import CommentDeleteApiView, CommentReplyApiView, ListingCommentApiView

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
]

from django.urls import path

from interactions.views import CommentCreateView, CommentDeleteView, CommentReplyView

app_name = "interactions"

urlpatterns = [
    path(
        "listing/<int:listing_id>/create",
        CommentCreateView.as_view(),
        name="comment_create",
    ),
    path("<int:pk>/reply", CommentReplyView.as_view(), name="reply"),
    path("<int:pk>/delete", CommentDeleteView.as_view(), name="comment_delete"),
]

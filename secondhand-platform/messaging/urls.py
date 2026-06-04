from django.urls import path

from messaging.views import (
    ConversationDetailView,
    ConversationListView,
    StartConversationView,
)

app_name = "messaging"

urlpatterns = [
    path("", ConversationListView.as_view(), name="conversation_list"),
    path(
        "start/<int:user_id>/",
        StartConversationView.as_view(),
        name="start_conversation",
    ),
    path(
        "<int:pk>/",
        ConversationDetailView.as_view(),
        name="conversation_detail",
    ),
]

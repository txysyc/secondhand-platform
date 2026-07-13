"""messaging 应用 API 路由。"""

from django.urls import path

from messaging.views import (
    ConversationDetailAPIView,
    ConversationListCreateAPIView,
    ConversationMessageListCreateAPIView,
    ConversationReadAPIView,
)

urlpatterns = [
    path(
        "conversations/",
        ConversationListCreateAPIView.as_view(),
        name="messaging_conversations",
    ),
    path(
        "conversations/<int:pk>/",
        ConversationDetailAPIView.as_view(),
        name="messaging_conversation_detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        ConversationMessageListCreateAPIView.as_view(),
        name="messaging_conversation_messages",
    ),
    path(
        "conversations/<int:pk>/read/",
        ConversationReadAPIView.as_view(),
        name="messaging_conversation_read",
    ),
]


"""messaging 应用 API 路由。"""

from django.urls import path

from messaging.views import (
    ConversationDetailApiView,
    ConversationListCreateApiView,
    ConversationMessageListCreateApiView,
    ConversationReadApiView,
)

urlpatterns = [
    path(
        "conversations/",
        ConversationListCreateApiView.as_view(),
        name="messaging_conversations",
    ),
    path(
        "conversations/<int:pk>/",
        ConversationDetailApiView.as_view(),
        name="messaging_conversation_detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        ConversationMessageListCreateApiView.as_view(),
        name="messaging_conversation_messages",
    ),
    path(
        "conversations/<int:pk>/read/",
        ConversationReadApiView.as_view(),
        name="messaging_conversation_read",
    ),
]


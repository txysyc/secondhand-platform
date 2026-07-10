"""messaging 应用 API 类视图。"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.mixins import PageNumberPaginationMixin
from api.throttles import MethodScopedThrottleMixin
from messaging.permissions import IsConversationParticipant
from messaging.serializers import (
    ConversationCreateSerializer,
    ConversationSerializer,
    PrivateMessageCreateSerializer,
    PrivateMessageSerializer,
)
from messaging.models import Conversation
from messaging.selectors import (
    DEFAULT_MESSAGE_WINDOW_SIZE,
    get_conversation_for_user,
    get_conversation_message_cursor_page,
    get_user_conversations,
)
from messaging.services import (
    create_private_message,
    get_or_create_conversation,
    mark_conversation_read,
    serialize_private_message,
)


class ConversationListCreateApiView(MethodScopedThrottleMixin, PageNumberPaginationMixin, APIView):
    """当前用户会话列表与发起会话。"""

    permission_classes = [IsAuthenticated]
    method_throttle_scopes = {"POST": "message_send"}
    max_page_size = 50

    def get(self, request):
        return self.paginate(
            request,
            get_user_conversations(request.user),
            ConversationSerializer,
        )

    def post(self, request):
        serializer = ConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = get_or_create_conversation(
            request.user,
            serializer.validated_data["target_user"],
        )
        response_serializer = ConversationSerializer(
            get_conversation_for_user(request.user, conversation.pk),
            context={"request": request},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class _ConversationParticipantApiView(APIView):
    """需要会话参与者身份的 API 基类。"""

    permission_classes = [IsAuthenticated, IsConversationParticipant]

    def get_object(self, request, pk):
        conversation = get_object_or_404(
            Conversation.objects.select_related(
                "participant_a",
                "participant_a__profile",
                "participant_b",
                "participant_b__profile",
            ),
            pk=pk,
        )
        self.check_object_permissions(request, conversation)
        return conversation


class ConversationDetailApiView(_ConversationParticipantApiView):
    """会话详情。"""

    def get(self, request, pk):
        conversation = self.get_object(request, pk)
        serializer = ConversationSerializer(conversation, context={"request": request})
        return Response(serializer.data)


class ConversationMessageListCreateApiView(
    MethodScopedThrottleMixin,
    _ConversationParticipantApiView,
):
    """会话消息列表与 HTTP 发送消息。"""

    method_throttle_scopes = {"POST": "message_send"}

    def get(self, request, pk):
        conversation = self.get_object(request, pk)
        try:
            page = get_conversation_message_cursor_page(
                conversation,
                before_id=request.query_params.get("before_id"),
                after_id=request.query_params.get("after_id"),
                latest=True,
                limit=request.query_params.get("limit", DEFAULT_MESSAGE_WINDOW_SIZE),
            )
        except ValueError as exc:
            raise ValidationError(str(exc))
        return Response(
            {
                "results": PrivateMessageSerializer(
                    page["results"],
                    many=True,
                    context={"request": request},
                ).data,
                "before_cursor": page["before_cursor"],
                "after_cursor": page["after_cursor"],
                "has_more_before": page["has_more_before"],
                "has_more_after": page["has_more_after"],
                "page_size": page["page_size"],
            }
        )

    def post(self, request, pk):
        conversation = self.get_object(request, pk)
        serializer = PrivateMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = create_private_message(
            request.user,
            conversation,
            serializer.validated_data["content"],
        )
        return Response(serialize_private_message(message), status=status.HTTP_201_CREATED)


class ConversationReadApiView(_ConversationParticipantApiView):
    """标记会话已读。"""

    def post(self, request, pk):
        conversation = self.get_object(request, pk)
        updated_count = mark_conversation_read(request.user, conversation)
        return Response({"updated_count": updated_count})


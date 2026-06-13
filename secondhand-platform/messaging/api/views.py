"""messaging 应用 API 类视图。"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from messaging.api.permissions import IsConversationParticipant
from messaging.api.serializers import (
    ConversationCreateSerializer,
    ConversationSerializer,
    PrivateMessageCreateSerializer,
    PrivateMessageSerializer,
)
from messaging.models import Conversation
from messaging.selectors import (
    get_conversation_for_user,
    get_conversation_messages,
    get_user_conversations,
)
from messaging.services import (
    create_private_message,
    get_or_create_conversation,
    mark_conversation_read,
    serialize_private_message,
)


class _ServiceErrorMixin:
    """把服务层异常转成稳定的 DRF 错误响应。"""

    def run_service(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DjangoValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else "请求处理失败"
            raise ValidationError(detail=message)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(detail=str(exc))


class _MessagingPaginatorMixin:
    """私信列表分页辅助。"""

    page_size = 20

    def paginate(self, request, queryset, serializer_class):
        page_number = request.query_params.get("page", 1)
        try:
            page_number = int(page_number)
        except (TypeError, ValueError):
            page_number = 1

        page_number = max(page_number, 1)
        total = queryset.count()
        start = (page_number - 1) * self.page_size
        end = start + self.page_size
        items = list(queryset[start:end])
        next_page = page_number + 1 if end < total else None
        previous_page = page_number - 1 if page_number > 1 else None
        return Response(
            {
                "count": total,
                "next": None if next_page is None else self._page_url(request, next_page),
                "previous": (
                    None
                    if previous_page is None
                    else self._page_url(request, previous_page)
                ),
                "results": serializer_class(
                    items,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )

    def _page_url(self, request, page_number):
        query_params = request.query_params.copy()
        query_params["page"] = page_number
        return f"{request.build_absolute_uri(request.path)}?{query_params.urlencode()}"


class ConversationListCreateApiView(
    _ServiceErrorMixin,
    _MessagingPaginatorMixin,
    APIView,
):
    """当前用户会话列表与发起会话。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return self.paginate(
            request,
            get_user_conversations(request.user),
            ConversationSerializer,
        )

    def post(self, request):
        serializer = ConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = self.run_service(
            get_or_create_conversation,
            request.user,
            serializer.validated_data["target_user"],
        )
        response_serializer = ConversationSerializer(
            get_conversation_for_user(request.user, conversation.pk),
            context={"request": request},
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class _ConversationParticipantApiView(_ServiceErrorMixin, APIView):
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
    _ConversationParticipantApiView,
    _MessagingPaginatorMixin,
):
    """会话消息列表与 HTTP 发送消息。"""

    def get(self, request, pk):
        conversation = self.get_object(request, pk)
        messages = get_conversation_messages(conversation)
        return self.paginate(request, messages, PrivateMessageSerializer)

    def post(self, request, pk):
        conversation = self.get_object(request, pk)
        serializer = PrivateMessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = self.run_service(
            create_private_message,
            request.user,
            conversation,
            serializer.validated_data["content"],
        )
        return Response(serialize_private_message(message), status=status.HTTP_201_CREATED)


class ConversationReadApiView(_ConversationParticipantApiView):
    """标记会话已读。"""

    def post(self, request, pk):
        conversation = self.get_object(request, pk)
        updated_count = self.run_service(mark_conversation_read, request.user, conversation)
        return Response({"updated_count": updated_count})

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from messaging.forms import PrivateMessageForm
from messaging.models import Conversation
from messaging.selectors import (
    get_conversation_for_user,
    get_conversation_messages,
    get_user_conversations,
)
from messaging.services import (
    create_private_message,
    first_error_message,
    get_or_create_conversation,
    mark_conversation_read,
)


class ConversationListView(LoginRequiredMixin, ListView):
    """私信入口页，有会话时直达最近一条会话。"""

    template_name = "messaging/conversation_list.html"
    context_object_name = "conversations"
    paginate_by = 20

    def get_queryset(self):
        """返回当前登录用户参与的会话列表。"""

        return get_user_conversations(self.request.user)

    def get(self, request, *args, **kwargs):
        """有最近会话时跳转详情页，否则渲染空会话列表。"""

        latest_conversation = self.get_queryset().first()
        if latest_conversation is not None:
            return redirect(
                "messaging:conversation_detail",
                pk=latest_conversation.pk,
            )
        return super().get(request, *args, **kwargs)


class StartConversationView(LoginRequiredMixin, View):
    """从卖家入口发起或复用一对一私信会话。"""

    http_method_names = ["post"]

    def get(self, request, *args, **kwargs):
        """拒绝通过 GET 发起私信会话。"""

        return HttpResponseNotAllowed(["POST"])

    def post(self, request, user_id):
        """创建或复用与目标用户的会话并跳转到详情页。"""

        target_user = get_object_or_404(get_user_model(), pk=user_id)
        try:
            conversation = get_or_create_conversation(request.user, target_user)
        except ValidationError as error:
            messages.error(request, first_error_message(error, "无法发起私信"))
            return redirect("public_profile", user_id=user_id)
        return redirect("messaging:conversation_detail", pk=conversation.pk)


class ConversationDetailView(LoginRequiredMixin, View):
    """私信会话详情页，支持 HTTP 回退发送消息。"""

    template_name = "messaging/conversation_detail.html"
    form_class = PrivateMessageForm

    def get_conversation(self, request, pk):
        """读取当前用户有权限访问的会话，不存在时返回 404。"""

        try:
            return get_conversation_for_user(request.user, pk)
        except PermissionDenied:
            raise
        except Conversation.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        """渲染会话详情并把收到的未读消息标记为已读。"""

        conversation = self.get_conversation(request, pk)
        mark_conversation_read(request.user, conversation)
        context = self.get_context_data(request, conversation, form=self.form_class())
        return render(request, self.template_name, context)

    def post(self, request, pk):
        """通过普通 HTTP POST 发送私信。"""

        conversation = self.get_conversation(request, pk)
        form = self.form_class(request.POST)
        if form.is_valid():
            try:
                create_private_message(
                    request.user,
                    conversation,
                    form.cleaned_data["content"],
                )
            except ValidationError as error:
                messages.error(request, first_error_message(error, "消息发送失败"))
            except PermissionDenied:
                raise
            else:
                messages.success(request, "消息已发送")
            return redirect("messaging:conversation_detail", pk=conversation.pk)

        context = self.get_context_data(request, conversation, form=form)
        return render(request, self.template_name, context)

    def get_context_data(self, request, conversation, form):
        """构造私信详情页和左侧会话列表所需上下文。"""

        other_user = conversation.other_participant(request.user)
        return {
            "conversation": conversation,
            "conversations": get_user_conversations(request.user),
            "other_user": other_user,
            "private_messages": get_conversation_messages(conversation),
            "form": form,
        }

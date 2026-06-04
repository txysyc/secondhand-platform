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
    get_or_create_conversation,
    mark_conversation_read,
)


class ConversationListView(LoginRequiredMixin, ListView):
    template_name = "messaging/conversation_list.html"
    context_object_name = "conversations"
    paginate_by = 20

    def get_queryset(self):
        return get_user_conversations(self.request.user)


class StartConversationView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, user_id):
        target_user = get_object_or_404(get_user_model(), pk=user_id)
        try:
            conversation = get_or_create_conversation(request.user, target_user)
        except ValidationError as error:
            messages.error(request, _first_error_message(error, "无法发起私信"))
            return redirect("public_profile", user_id=user_id)
        return redirect("messaging:conversation_detail", pk=conversation.pk)


class ConversationDetailView(LoginRequiredMixin, View):
    template_name = "messaging/conversation_detail.html"
    form_class = PrivateMessageForm

    def get_conversation(self, request, pk):
        try:
            return get_conversation_for_user(request.user, pk)
        except PermissionDenied:
            raise
        except Conversation.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        conversation = self.get_conversation(request, pk)
        mark_conversation_read(request.user, conversation)
        context = self.get_context_data(request, conversation, form=self.form_class())
        return render(request, self.template_name, context)

    def post(self, request, pk):
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
                messages.error(request, _first_error_message(error, "消息发送失败"))
            except PermissionDenied:
                raise
            else:
                messages.success(request, "消息已发送")
            return redirect("messaging:conversation_detail", pk=conversation.pk)

        context = self.get_context_data(request, conversation, form=form)
        return render(request, self.template_name, context)

    def get_context_data(self, request, conversation, form):
        other_user = conversation.other_participant(request.user)
        return {
            "conversation": conversation,
            "other_user": other_user,
            "private_messages": get_conversation_messages(conversation),
            "form": form,
        }


def _first_error_message(error, fallback):
    messages_list = getattr(error, "messages", None)
    if messages_list:
        return messages_list[0]
    if error.args:
        return str(error.args[0])
    return fallback

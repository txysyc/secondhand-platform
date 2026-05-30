from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib import messages

from interactions.forms import CommentForm
from interactions.models import Comment
from interactions.services import create_comment, delete_comment, create_reply
from catalog.models import Listing


# Create your views here.
class CommentCreateView(LoginRequiredMixin, View):
    model = Comment
    from_class = CommentForm
    http_method_names = ["post"]

    def post(self, request, listing_id):
        form = self.from_class(data=request.POST)
        listing = get_object_or_404(
            Listing.objects.select_related("category"),
            pk=listing_id,
            category__is_active=True,
        )

        if form.is_valid():
            try:
                create_comment(
                    request.user, listing, form.cleaned_data.get("content", "")
                )
            except ValidationError as error:
                messages.error(request, _first_error_message(error, "留言发布失败"))
                return redirect("catalog:listing_detail", pk=listing_id)
            except PermissionDenied:
                messages.error(request, "无权发布留言")
                return redirect("catalog:listing_detail", pk=listing_id)
            messages.success(request, "留言已发布")
            return redirect("catalog:listing_detail", pk=listing_id)
        messages.error(request, _first_form_error_message(form, "留言发布失败"))
        return redirect("catalog:listing_detail", pk=listing_id)


class CommentDeleteView(LoginRequiredMixin, View):
    model = Comment
    http_method_names = ["post"]

    def post(self, request, pk):
        comment = get_object_or_404(Comment, pk=pk)
        listing_id = comment.listing_id
        try:
            delete_comment(request.user, comment)
        except ValidationError as error:
            messages.error(request, _first_error_message(error, "留言删除失败"))
            return redirect("catalog:listing_detail", listing_id)
        messages.success(request, "留言已删除")
        return redirect("catalog:listing_detail", listing_id)


def _first_form_error_message(form, fallback: str):
    """处理表单校验未通过时的错误"""
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return fallback


def _first_error_message(error, fallback: str):
    """校验服务层异常错误"""
    messages_list = getattr(error, "messages", None)
    if messages_list:
        return messages_list[0]
    if error.args:
        return str(error.args[0])
    return fallback


class CommentReplyView(LoginRequiredMixin, View):
    http_method_names = ["post"]
    form_class = CommentForm
    model = Comment

    def post(self, request, pk):
        form = self.form_class(request.POST)
        comment = get_object_or_404(
            Comment.objects.select_related(
                "listing", "listing__category", "listing__owner"
            ),
            pk=pk,
        )

        if form.is_valid():
            content = form.cleaned_data.get("content", "")
            try:
                create_reply(request.user, comment, content)
            except ValidationError as error:
                messages.error(request, _first_error_message(error, "留言回复失败"))
                return redirect("catalog:listing_detail", pk=comment.listing_id)
            except PermissionDenied as error:
                messages.error(request, _first_error_message(error, "无权回复留言"))
                return redirect("catalog:listing_detail", pk=comment.listing_id)
            messages.success(request, "留言回复成功")
            return redirect("catalog:listing_detail", pk=comment.listing_id)

        messages.error(request, _first_form_error_message(form, "留言回复失败"))
        return redirect("catalog:listing_detail", pk=comment.listing_id)

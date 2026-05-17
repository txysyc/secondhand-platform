from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from catalog.forms import ListingForm, ListingImageFormSet
from catalog.models import Listing
from catalog.selectors import get_owner_listing_groups
from catalog.services import (
    INTENT_PUBLISH,
    INTENT_SAVE_CHANGES,
    ACTION_RESTORE_ACTIVE,
    ACTION_WITHDRAW,
    change_listing_status,
    create_listing,
    delete_listing,
    ensure_listing_owner,
    update_listing,
)


class ListingCreateView(LoginRequiredMixin, View):
    """登录用户创建商品的页面。"""

    template_name = "catalog/listing_form.html"
    form_class = ListingForm
    image_formset_class = ListingImageFormSet
    image_formset_prefix = "images"

    def get(self, request):
        form = self.form_class()
        formset = self.image_formset_class(prefix=self.image_formset_prefix)
        context = self.get_context_data(form=form, formset=formset)

        return render(request, self.template_name, context=context)

    def post(self, request):
        form = self.form_class(request.POST)
        formset = self.image_formset_class(
            request.POST, request.FILES, prefix=self.image_formset_prefix
        )
        context = self.get_context_data(form=form, formset=formset)

        if form.is_valid() and formset.is_valid():
            intent = request.POST.get("intent")
            try:
                listing = create_listing(request.user, form, formset, intent)
            except ValidationError as error:
                form.add_error(None, error)
                return render(request, self.template_name, context=context)

            if intent == INTENT_PUBLISH:
                messages.success(request, "商品已发布")
            else:
                messages.success(request, "草稿保存成功")
            return redirect("catalog:listing_edit", pk=listing.pk)

        return render(request, self.template_name, context=context)

    def get_context_data(self, **kwargs):
        return {
            **kwargs,
            "is_create": True,
            "page_eyebrow": "商品发布",
            "page_title": "准备发布内容",
            "panel_title": "创建商品",
        }


class ListingUpdateView(LoginRequiredMixin, View):
    """登录用户编辑自己商品的页面。"""

    template_name = "catalog/listing_form.html"
    form_class = ListingForm
    image_formset_class = ListingImageFormSet
    image_formset_prefix = "images"
    model = Listing

    def get_listing(self, request, pk):
        listing = get_object_or_404(self.model, pk=pk)
        ensure_listing_owner(request.user, listing)
        return listing

    def get(self, request, pk):
        listing = self.get_listing(request, pk)
        form = self.form_class(instance=listing)
        formset = self.image_formset_class(
            instance=listing, prefix=self.image_formset_prefix
        )
        context = self.get_context_data(listing=listing, form=form, formset=formset)

        return render(request, self.template_name, context=context)

    def post(self, request, pk):
        listing = self.get_listing(request, pk)
        form = self.form_class(request.POST, instance=listing)
        formset = self.image_formset_class(
            request.POST,
            request.FILES,
            instance=listing,
            prefix=self.image_formset_prefix,
        )
        context = self.get_context_data(listing=listing, form=form, formset=formset)

        if form.is_valid() and formset.is_valid():
            intent = request.POST.get("intent")
            try:
                listing = update_listing(request.user, listing, form, formset, intent)
            except ValidationError as error:
                form.add_error(None, error)
                return render(request, self.template_name, context=context)

            if intent == INTENT_PUBLISH:
                messages.success(request, "商品已发布")
            elif intent == INTENT_SAVE_CHANGES:
                messages.success(request, "修改保存成功")
            else:
                messages.success(request, "草稿保存成功")
            return redirect("catalog:listing_edit", pk=listing.pk)

        return render(request, self.template_name, context=context)

    def get_context_data(self, listing, **kwargs):
        return {
            **kwargs,
            "listing": listing,
            "is_create": False,
            "is_active_listing": listing.status == Listing.Status.ACTIVE,
            "page_eyebrow": listing.get_status_display(),
            "page_title": listing.title,
            "panel_title": "编辑商品",
        }


class ListingDeleteView(LoginRequiredMixin, View):
    """登录用户删除自己商品的确认页和动作。"""

    template_name = "catalog/listing_confirm_delete.html"
    model = Listing

    def get_listing(self, request, pk):
        listing = get_object_or_404(self.model, pk=pk)
        ensure_listing_owner(request.user, listing)
        return listing

    def get(self, request, pk):
        listing = self.get_listing(request, pk)
        return render(request, self.template_name, {"listing": listing})

    def post(self, request, pk):
        listing = self.get_listing(request, pk)
        try:
            delete_listing(request.user, listing)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect("catalog:listing_edit", pk=listing.pk)

        messages.success(request, "成功删除商品")
        return redirect("users:profile")


class MyListingListView(LoginRequiredMixin, View):
    """卖家“我的商品”分组面板。"""

    template_name = "catalog/my_listing_list.html"

    def get(self, request):
        listing_groups = get_owner_listing_groups(request.user)
        context = {
            "listing_groups": listing_groups,
            "action_withdraw": ACTION_WITHDRAW,
            "action_restore_active": ACTION_RESTORE_ACTIVE,
        }
        return render(request, self.template_name, context)


class ListingStatusUpdateView(LoginRequiredMixin, View):
    """处理“下架”“重新上架”等卖家手动状态动作的 POST 入口。"""

    model = Listing
    http_method_names = ["post"]

    SUCCESS_MESSAGES = {
        ACTION_WITHDRAW: "商品已下架",
        ACTION_RESTORE_ACTIVE: "商品已重新上架",
    }

    def http_method_not_allowed(self, request, *args, **kwargs):
        # 显式 405 响应，确保 GET / PUT 等无法触发状态变更。
        return HttpResponseNotAllowed(["POST"])

    def post(self, request, pk):
        listing = get_object_or_404(
            self.model.objects.select_related("category"), pk=pk
        )
        ensure_listing_owner(request.user, listing)

        action = request.POST.get("action", "")
        try:
            change_listing_status(request.user, listing, action)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            return redirect("catalog:my_listing_list")

        messages.success(request, self.SUCCESS_MESSAGES.get(action, "操作成功"))
        return redirect("catalog:my_listing_list")

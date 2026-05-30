from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.query import QuerySet
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, DetailView
from django.conf import settings

from catalog.forms import ListingForm, ListingImageFormSet, ListingFilterForm
from catalog.models import Listing
from catalog.selectors import get_owner_listing_groups, get_publish_listing_queryset
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
from orders.services import create_order
from interactions.forms import CommentForm
from interactions.selectors import get_listing_comments
from interactions.services import can_interact_with_listing


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


class ListingListView(ListView):
    model = Listing
    template_name = "catalog/listing_list.html"
    context_object_name = "listings"
    paginate_by = 12
    form = ListingFilterForm

    def get_queryset(self) -> QuerySet[Any]:
        self._filter_form = self.form(self.request.GET)
        if self._filter_form.is_valid():
            cleaned_data = self._filter_form.cleaned_data
            return get_publish_listing_queryset(cleaned_data)
        return get_publish_listing_queryset()

    def paginate_queryset(
        self,
        queryset: QuerySet[Any],
        page_size: int,
    ) -> tuple[Paginator, Any, QuerySet[Any], bool]:
        paginator = self.get_paginator(
            queryset,
            page_size,
            orphans=self.get_paginate_orphans(),
            allow_empty_first_page=self.get_allow_empty(),
        )
        page = paginator.get_page(self.request.GET.get(self.page_kwarg))
        return paginator, page, page.object_list, page.has_other_pages()

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop(self.page_kwarg, None)

        context["querystring_without_page"] = query_params.urlencode()
        context["filter_form"] = self._filter_form
        context["active_filters"] = self._build_active_filters_summary()
        return context

    def _build_active_filters_summary(self) -> str:
        if not self._filter_form.is_valid():
            return ""
        parts = []
        data = self._filter_form.cleaned_data
        if data.get("q"):
            parts.append(f"关键词「{data['q']}」")
        if data.get("category"):
            parts.append(f"分类「{data['category'].name}」")
        if data.get("item_type"):
            item_type_labels = dict(self._filter_form.fields["item_type"].choices)
            parts.append(
                f"类型「{item_type_labels.get(data['item_type'], data['item_type'])}」"
            )
        raw_min = self.request.GET.get("min_price")
        raw_max = self.request.GET.get("max_price")
        if raw_min:
            parts.append(f"最低价 ¥{data['min_price']}")
        if raw_max:
            parts.append(f"最高价 ¥{data['max_price']}")
        sort_val = data.get("sort")
        sort_labels = dict(self._filter_form.fields["sort"].choices)
        if sort_val and sort_val != "newest":
            parts.append(f"排序「{sort_labels.get(sort_val, sort_val)}」")
        return "、".join(parts)


class ListingDetailView(DetailView):
    template_name = "catalog/listing_detail.html"
    model = Listing
    context_object_name = "listing"

    def get_queryset(self) -> QuerySet[Any]:
        queryset = self.model.objects.select_related(
            "category", "owner", "owner__profile"
        ).prefetch_related("images")

        public_filter = Q(
            status__in=[
                Listing.Status.ACTIVE,
                Listing.Status.RESERVED,
                Listing.Status.SOLD,
            ],
            category__is_active=True,
        )

        user = self.request.user
        if user.is_authenticated:
            owner_withdrawn_filter = Q(owner=user, status=Listing.Status.WITHDRAWN)
            return queryset.filter(public_filter | owner_withdrawn_filter)

        return queryset.filter(public_filter)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        listing = self.object
        user = self.request.user
        is_seller = user.is_authenticated and listing.owner_id == user.id
        # 获取所属的评论
        comments = get_listing_comments(listing)
        can_comment = can_interact_with_listing(listing)
        if user.is_authenticated:
            context.update(
                {
                    "comment_form": CommentForm(),
                    "reply_form": CommentForm(),
                }
            )
        # 购买链接
        purchase_path = f"/listings/{listing.pk}/purchase/"
        purchase_url = purchase_path
        purchase_disabled_reason = ""
        # 判断是否可以购买
        can_purchase = listing.status == Listing.Status.ACTIVE and not is_seller
        if can_purchase and not user.is_authenticated:
            purchase_url = (
                f"{reverse('users:login')}?{urlencode({'next': purchase_path})}"
            )
        elif is_seller:
            purchase_disabled_reason = "不能购买自己发布的商品"
        elif listing.status == Listing.Status.RESERVED:
            purchase_disabled_reason = "商品正在交易中，暂时无法购买"
        elif listing.status == Listing.Status.SOLD:
            purchase_disabled_reason = "商品已售出"
        elif listing.status == Listing.Status.WITHDRAWN:
            purchase_disabled_reason = "商品已下架"

        context.update(
            {
                "is_seller": is_seller,
                "can_comment": can_comment,
                "can_purchase": can_purchase,
                "purchase_url": purchase_url,
                "purchase_disabled_reason": purchase_disabled_reason,
                "purchase_requires_login": can_purchase and not user.is_authenticated,
                "comments": comments,
            }
        )
        return context


class PurchaseConfirmView(LoginRequiredMixin, View):
    """确认购买"""

    template_name = "catalog/purchase_confirm.html"

    def get_object(self, pk):
        return get_object_or_404(Listing, pk=pk)

    def get_context_data(self, listing):
        context = {
            "listing": listing,
            "seller": listing.owner,
            "hit": "请确认是否购买该商品",
        }
        return context

    def get(self, request, pk):
        listing = self.get_object(pk)
        if listing.status != Listing.Status.ACTIVE:
            messages.error(request, "该商品当前不可购买")
            return redirect("catalog:listing_detail", pk=pk)
        if request.user == listing.owner:
            messages.error(request, "不能购买自己发布的商品")
            return redirect("catalog:listing_detail", pk=pk)
        context = self.get_context_data(listing)
        return render(request, self.template_name, context)

    def post(self, request, pk):
        listing = self.get_object(pk)

        try:
            order = create_order(request.user, listing)
        except PermissionDenied:
            messages.error(request, "不能购买自己发布的商品")
            return redirect("catalog:listing_detail", pk=pk)
        except ValidationError:
            messages.error(request, "该商品当前不可购买")
            return redirect("catalog:listing_detail", pk=pk)

        return redirect("orders:order_detail", pk=order.pk)

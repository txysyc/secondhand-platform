from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages

from catalog.forms import ListingDraftForm, ListingImageFormSet
from catalog.services import create_listing_draft


class ListingCreateView(LoginRequiredMixin, View):
    """登录用户创建商品草稿的页面。"""

    template_name = "catalog/listing_form.html"
    form_class = ListingDraftForm
    image_formset_class = ListingImageFormSet
    image_formset_prefix = "images"

    def get(self, request):
        form = self.form_class()
        formset = self.image_formset_class(prefix=self.image_formset_prefix)

        context = {"form": form, "formset": formset}

        return render(request, self.template_name, context=context)

    def post(self, request):
        form = self.form_class(request.POST)
        formset = self.image_formset_class(
            request.POST, request.FILES, prefix=self.image_formset_prefix
        )
        context = {"form": form, "formset": formset}

        if form.is_valid() and formset.is_valid():
            # owner 和 status 不从 POST 读取，由服务层按当前登录用户和草稿状态写入。
            create_listing_draft(request.user, form, formset)
            messages.success(request, "草稿保存成功")
            return redirect("users:profile")

        return render(request, self.template_name, context=context)

from django.db import transaction
from django.forms import BaseInlineFormSet

from catalog.forms import ListingDraftForm
from catalog.models import Listing
from users.models import User


def create_listing_draft(
    owner: User, form: ListingDraftForm, formset: BaseInlineFormSet
):
    """原子化创建商品草稿和图片，所有者和状态由服务层强制写入。"""

    instance = form.save(commit=False)
    instance.status = Listing.Status.DRAFT
    instance.owner = owner

    with transaction.atomic():
        instance.save()
        # 新建商品先保存后再绑定 formset，图片才能获得所属商品外键。
        formset.instance = instance

        # 表单集已经校验数量，这里保留服务层保护，避免绕过表单直接调用服务。
        if _count_formset_images(formset) > 6:
            raise ValueError("最多只能上传6张图片")

        images = formset.save(commit=False)

        for sort_order, image in enumerate(images):
            image.listing = instance
            image.sort_order = sort_order
            image.save()

        for deleted_image in formset.deleted_objects:
            deleted_image.delete()

    return instance


def _count_formset_images(formset) -> int:
    """统计实际上传且未标记删除的图片数量。"""

    count = 0
    for form in formset.forms:
        if not hasattr(form, "cleaned_data"):
            continue
        if form.cleaned_data.get("DELETE"):
            continue
        if form.cleaned_data.get("image"):
            count += 1
    return count

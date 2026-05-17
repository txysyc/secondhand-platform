from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from catalog.models import Listing, ListingImage
from catalog.selectors import get_active_categories

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_IMAGE_COUNT = 6


class ListingForm(forms.ModelForm):
    """商品字段表单，集中处理类型差异字段和用户输入校验。"""

    class Meta:
        model = Listing
        fields = [
            "title",
            "category",
            "item_type",
            "price",
            "condition",
            "description",
            "delivery_notes",
            "physical_delivery_method",
            "virtual_valid_until",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        category = self.fields["category"]

        # 新建草稿只能选择启用分类；伪造停用分类提交也会被 ModelChoiceField 拒绝。
        if isinstance(category, forms.ModelChoiceField):
            category.queryset = get_active_categories()

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is not None and price <= 0:
            raise forms.ValidationError("价格必须大于0")
        return price

    def clean(self):
        cleaned_data = super().clean()
        item_type = cleaned_data.get("item_type")

        # 类型切换时主动清空不适用字段，避免隐藏字段的旧值写入草稿。
        if item_type == Listing.ItemType.PHYSICAL:
            if not cleaned_data.get("condition"):
                self.add_error("condition", "实体商品必须填写成色")
            if not cleaned_data.get("physical_delivery_method"):
                self.add_error("physical_delivery_method", "实体商品必须选择交付方式")
            cleaned_data["virtual_valid_until"] = None
        if item_type == Listing.ItemType.VIRTUAL:
            if not cleaned_data.get("virtual_valid_until"):
                self.add_error("virtual_valid_until", "虚拟商品需要填写有效期")
            cleaned_data["condition"] = None
            cleaned_data["physical_delivery_method"] = None

        # 只在虚拟商品分支保留有效期后再校验日期，避免实体商品被隐藏旧值阻塞。
        virtual_valid_until = cleaned_data.get("virtual_valid_until")
        if virtual_valid_until and virtual_valid_until < timezone.localdate():
            self.add_error("virtual_valid_until", "有效期不能早于当前日期")

        return cleaned_data


class ListingImageForm(forms.ModelForm):
    """单张商品图片表单，负责文件级校验。"""

    class Meta:
        model = ListingImage
        fields = ["image"]

    def clean_image(self):
        image = self.cleaned_data.get("image")

        if image is None:
            return None

        if image.size > MAX_IMAGE_SIZE:
            raise forms.ValidationError("单张图片不能大于5MB")
        return image


class BaseListingImageFormSet(BaseInlineFormSet):
    """校验商品图片表单集。"""

    def clean(self):
        """限制实际上传的图片数量。

        `total_form_count()` 会包含空表单；这里只统计有图片且未标记删除的表单。
        """

        super().clean()

        image_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            if form.instance.pk or form.cleaned_data.get("image"):
                image_count += 1

        if image_count > MAX_IMAGE_COUNT:
            raise forms.ValidationError(f"最多只能上传 {MAX_IMAGE_COUNT} 张图片。")


ListingImageFormSet = inlineformset_factory(
    Listing,
    ListingImage,
    form=ListingImageForm,
    formset=BaseListingImageFormSet,
    fields=["image"],
    extra=0,
    max_num=MAX_IMAGE_COUNT,
    validate_max=True,  # 开启服务端数量强校验，防止伪造 management form 绕过上限。
    can_delete=True,
)

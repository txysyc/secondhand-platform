from typing import Any

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone
from django.core.exceptions import ValidationError

from catalog.models import Category, Listing, ListingImage
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
        """初始化表单并把分类选项限制为当前启用分类。"""

        super().__init__(*args, **kwargs)
        category = self.fields["category"]

        # 新建草稿只能选择启用分类；伪造停用分类提交也会被 ModelChoiceField 拒绝。
        if isinstance(category, forms.ModelChoiceField):
            category.queryset = get_active_categories()

    def clean_price(self):
        """校验商品价格必须为正数。"""

        price = self.cleaned_data.get("price")
        if price is not None and price <= 0:
            raise forms.ValidationError("价格必须大于0")
        return price

    def clean(self):
        """按商品类型校验并清理不适用的差异字段。"""

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
        """校验单张商品图片的大小限制。"""

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


class ListingFilterForm(forms.Form):
    """公开商品列表筛选表单。"""

    q = forms.CharField(max_length=100, required=False, label="关键字")
    category = forms.ModelChoiceField(
        Category.objects.none(), required=False, label="分类"
    )
    item_type = forms.ChoiceField(
        choices=[("", "全部类型")] + list(Listing.ItemType.choices),
        required=False,
        label="商品类型",
        initial="",
    )
    max_price = forms.DecimalField(
        max_value=99999999, min_value=0, required=False, label="最高价格"
    )
    min_price = forms.DecimalField(
        min_value=0, max_value=99999999, required=False, label="最低价格"
    )
    sort = forms.ChoiceField(
        choices=[
            ("newest", "按时间倒序"),
            ("oldest", "按时间正序"),
            ("price_asc", "按价格升序"),
            ("price_desc", "按价格降序"),
        ],
        required=False,
        label="排序",
        initial="newest",
    )
    page = forms.IntegerField(min_value=1, required=False, label="页码")

    def __init__(self, *args, **kwargs):
        """初始化筛选表单并加载当前启用分类作为可选项。"""

        super().__init__(*args, **kwargs)
        category = self.fields["category"]
        if isinstance(category, forms.ModelChoiceField):
            category.queryset = get_active_categories()

    def clean_q(self):
        """去除关键词两端空白。"""

        q: str = self.cleaned_data.get("q", "")
        q = q.strip()
        return q

    def clean_max_price(self):
        """为空的最高价填充默认上限。"""

        max_price = self.cleaned_data.get("max_price")
        if max_price is None:
            max_price = 99999999
        return max_price

    def clean_min_price(self):
        """为空的最低价填充默认下限。"""

        min_price = self.cleaned_data.get("min_price")
        if min_price is None:
            min_price = 0
        return min_price

    def clean_page(self):
        """为空的页码填充第一页。"""

        page = self.cleaned_data.get("page")
        if page is None:
            page = 1
        return page

    def clean(self) -> dict[str, Any]:
        """校验价格区间的上下限关系。"""

        cleaned_data = super().clean()

        max_price = cleaned_data.get("max_price")
        min_price = cleaned_data.get("min_price")

        if max_price is not None and min_price is not None and max_price < min_price:
            raise ValidationError("最高价格不得低于最低价格")

        return cleaned_data

"""catalog 商品列表筛选器。"""

from datetime import datetime, time

import django_filters
from django import forms
from django.db.models import Q
from django.utils import timezone

from catalog.models import Category, Listing
from catalog.selectors import get_active_categories

MAX_LISTING_SEARCH_LENGTH = 50


class ListingDateTimeField(forms.DateTimeField):
    """兼容 ISO 日期时间和纯日期的发布时间筛选字段。"""

    input_formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    default_error_messages = {
        "invalid": "请输入有效的发布时间",
    }


class ListingDateTimeFilter(django_filters.DateTimeFilter):
    """为发布时间区间复用自定义中文错误日期字段。"""

    field_class = ListingDateTimeField


class ListingFilterForm(forms.Form):
    """公开商品列表筛选表单，集中处理跨字段参数校验。"""

    def clean_q(self):
        """去除搜索词首尾空白，并限制关键词长度。"""

        value = (self.cleaned_data.get("q") or "").strip()
        if len(value) > MAX_LISTING_SEARCH_LENGTH:
            raise forms.ValidationError(
                f"搜索关键词不能超过{MAX_LISTING_SEARCH_LENGTH}个字符"
            )
        return value

    def clean(self):
        """校验价格区间和发布时间区间不能倒挂。"""

        cleaned_data = super().clean()
        min_price = cleaned_data.get("min_price")
        max_price = cleaned_data.get("max_price")
        published_after = cleaned_data.get("published_after")
        published_before = _normalize_plain_date_before(
            self.data.get("published_before"),
            cleaned_data.get("published_before"),
        )

        if min_price is not None and max_price is not None and max_price < min_price:
            self.add_error("max_price", "最高价格不得低于最低价格")

        if (
            published_after is not None
            and published_before is not None
            and published_before < published_after
        ):
            self.add_error("published_before", "发布时间截止不得早于发布时间起始")

        return cleaned_data


class ListingFilterSet(django_filters.FilterSet):
    """公开商品列表筛选参数。"""

    q = django_filters.CharFilter(method="filter_q", required=False)
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.none(),
        required=False,
    )
    item_type = django_filters.ChoiceFilter(
        choices=Listing.ItemType.choices,
        required=False,
    )
    min_price = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="gte",
        required=False,
    )
    max_price = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="lte",
        required=False,
    )
    published_after = ListingDateTimeFilter(
        field_name="published_at",
        lookup_expr="gte",
        required=False,
    )
    published_before = ListingDateTimeFilter(
        method="filter_published_before",
        required=False,
    )

    class Meta:
        model = Listing
        fields = [
            "q",
            "category",
            "item_type",
            "min_price",
            "max_price",
            "published_after",
            "published_before",
        ]
        form = ListingFilterForm

    def __init__(self, *args, **kwargs):
        """动态限定分类选项，保证停用分类不会成为有效筛选条件。"""

        super().__init__(*args, **kwargs)
        self.filters["category"].queryset = get_active_categories()

    def filter_q(self, queryset, name, value):
        """按标题或描述模糊搜索商品。"""

        if not value:
            return queryset
        return queryset.filter(Q(title__icontains=value) | Q(description__icontains=value))

    def filter_published_before(self, queryset, name, value):
        """按发布时间截止筛选，纯日期输入覆盖当天结束前的商品。"""

        if value is None:
            return queryset

        raw_value = self.data.get("published_before") if self.data is not None else ""
        value = _normalize_plain_date_before(raw_value, value)

        return queryset.filter(published_at__lte=value)


class MyListingFilterForm(forms.Form):
    """我的商品列表筛选表单，集中处理跨字段参数校验。"""

    def clean_q(self):
        """去除搜索词首尾空白，并限制关键词长度。"""

        value = (self.cleaned_data.get("q") or "").strip()
        if len(value) > MAX_LISTING_SEARCH_LENGTH:
            raise forms.ValidationError(
                f"搜索关键词不能超过{MAX_LISTING_SEARCH_LENGTH}个字符"
            )
        return value

    def clean(self):
        """校验价格区间和更新时间区间不能倒挂。"""

        cleaned_data = super().clean()
        min_price = cleaned_data.get("min_price")
        max_price = cleaned_data.get("max_price")
        updated_after = cleaned_data.get("updated_after")
        updated_before = cleaned_data.get("updated_before")

        if min_price is not None and max_price is not None and max_price < min_price:
            self.add_error("max_price", "最高价格不得低于最低价格")

        if (
            updated_after is not None
            and updated_before is not None
            and updated_before < updated_after
        ):
            self.add_error("updated_before", "更新时间截止不得早于更新时间起始")

        return cleaned_data


class MyListingFilterSet(django_filters.FilterSet):
    """当前用户自己的商品管理列表筛选参数。"""

    # 我的商品管理列表不展示已售出商品，因此筛选项同步排除 sold。
    MANAGEABLE_STATUS_CHOICES = [
        status_choice
        for status_choice in Listing.Status.choices
        if status_choice[0] != Listing.Status.SOLD
    ]

    q = django_filters.CharFilter(method="filter_q", required=False)
    status = django_filters.ChoiceFilter(
        choices=MANAGEABLE_STATUS_CHOICES,
        required=False,
    )
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.all(),
        required=False,
    )
    item_type = django_filters.ChoiceFilter(
        choices=Listing.ItemType.choices,
        required=False,
    )
    min_price = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="gte",
        required=False,
    )
    max_price = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="lte",
        required=False,
    )
    updated_after = ListingDateTimeFilter(
        field_name="updated_at",
        lookup_expr="gte",
        required=False,
    )
    updated_before = ListingDateTimeFilter(
        field_name="updated_at",
        lookup_expr="lte",
        required=False,
    )

    class Meta:
        model = Listing
        fields = [
            "q",
            "status",
            "category",
            "item_type",
            "min_price",
            "max_price",
            "updated_after",
            "updated_before",
        ]
        form = MyListingFilterForm

    def filter_q(self, queryset, name, value):
        """按标题或描述模糊搜索当前用户商品。"""

        if not value:
            return queryset
        return queryset.filter(Q(title__icontains=value) | Q(description__icontains=value))


def _normalize_plain_date_before(raw_value, value):
    """把纯日期截止值转换为当天结束时间。"""

    if value is None:
        return value
    if isinstance(raw_value, str) and len(raw_value) == 10:
        # 纯日期截止应包含当天，而不是只包含当天 00:00:00 之前的数据。
        return timezone.make_aware(
            datetime.combine(value.date(), time.max),
            timezone.get_current_timezone(),
        )
    return value

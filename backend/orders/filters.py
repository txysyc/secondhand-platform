"""orders 订单列表筛选器。"""

import django_filters
from django import forms
from django.db.models import Q

from orders.models import Order

MAX_ORDER_SEARCH_LENGTH = 50


class OrderFilterForm(forms.Form):
    """订单列表筛选表单，集中处理跨字段参数校验。"""

    def clean_q(self):
        """去除关键词首尾空白，并限制搜索长度。"""

        value = (self.cleaned_data.get("q") or "").strip()
        if len(value) > MAX_ORDER_SEARCH_LENGTH:
            raise forms.ValidationError(
                f"搜索关键词不能超过{MAX_ORDER_SEARCH_LENGTH}个字符"
            )
        return value

    def clean(self):
        """校验价格区间和创建时间区间不能倒挂。"""

        cleaned_data = super().clean()
        min_price = cleaned_data.get("min_price")
        max_price = cleaned_data.get("max_price")
        created_after = cleaned_data.get("created_after")
        created_before = cleaned_data.get("created_before")

        if min_price is not None and max_price is not None and max_price < min_price:
            self.add_error("max_price", "最高价格不得低于最低价格")

        if (
            created_after is not None
            and created_before is not None
            and created_before < created_after
        ):
            self.add_error("created_before", "创建时间截止不得早于创建时间起始")

        return cleaned_data


class OrderFilterSet(django_filters.FilterSet):
    """买家和卖家订单列表共用筛选参数。"""

    q = django_filters.CharFilter(method="filter_q", required=False)
    status = django_filters.ChoiceFilter(
        choices=Order.OrderStatus.choices,
        required=False,
    )
    created_after = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="gte",
        required=False,
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at",
        lookup_expr="lte",
        required=False,
    )
    min_price = django_filters.NumberFilter(
        field_name="order_price",
        lookup_expr="gte",
        required=False,
    )
    max_price = django_filters.NumberFilter(
        field_name="order_price",
        lookup_expr="lte",
        required=False,
    )

    class Meta:
        model = Order
        fields = [
            "q",
            "status",
            "created_after",
            "created_before",
            "min_price",
            "max_price",
        ]
        form = OrderFilterForm

    def filter_q(self, queryset, name, value):
        """按订单号、商品快照和交易双方名称搜索订单。"""

        if not value:
            return queryset

        query = (
            Q(listing_title_snapshot__icontains=value)
            | Q(buyer_display_name__icontains=value)
            | Q(seller_display_name__icontains=value)
            | Q(buyer__username__icontains=value)
            | Q(seller__username__icontains=value)
        )
        if value.isdigit():
            query |= Q(id=int(value))
        return queryset.filter(query)

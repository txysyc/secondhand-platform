from decimal import Decimal

import pytest
from io import BytesIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.admin import CategoryAdmin, ListingAdmin
from catalog.filters import ListingFilterSet
from catalog.models import Category, Listing, ListingImage
from catalog.selectors import (
    get_active_categories,
    get_public_listing_queryset,
    get_visible_listing_detail_queryset,
)
from orders.models import Order
from catalog.services import (
    ACTION_RESTORE_ACTIVE,
    ACTION_WITHDRAW,
    change_listing_status,
    delete_listing,
    publish_listing,
)
from interactions.models import ListingFavorite, ListingViewHistory
from users.models import User


pytestmark = pytest.mark.django_db

def build_png_image(name="listing.png", size=(16, 16)):
    """构造测试用 PNG 图片。"""

    buffer = BytesIO()
    image = Image.new("RGB", size, color="white")
    image.save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

class TestCatalogAPI:
    """P3 商品 API 测试。"""

    @pytest.fixture(autouse=True)
    def _setup_catalog_api_context(self, api_client, auth_headers, settings):
        """构造商品 API 测试上下文，并使用内存存储隔离上传文件。"""

        settings.STORAGES = {
            "default": {
                "BACKEND": "django.core.files.storage.InMemoryStorage",
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }
        self.api_client = api_client
        self.auth_headers = auth_headers
        self.seller = User.objects.create_user(
            username="apiseller",
            email="apiseller@example.com",
            password="StrongPass123",
        )
        self.other_user = User.objects.create_user(
            username="apiother",
            email="apiother@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="API数码")
        self.inactive_category = Category.objects.create(
            name="API停用分类",
            is_active=False,
        )

    def listing_payload(self, **overrides):
        data = {
            "title": "API二手相机",
            "category": self.category.id,
            "item_type": Listing.ItemType.PHYSICAL,
            "price": "388.00",
            "condition": Listing.Condition.LIKE_NEW,
            "description": "功能正常。",
            "delivery_notes": "地铁站面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "virtual_valid_until": None,
        }
        data.update(overrides)
        return data

    def create_listing(self, **overrides):
        data = {
            "owner": self.seller,
            "category": self.category,
            "title": "公开商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("99.00"),
            "condition": Listing.Condition.GOOD,
            "description": "公开描述",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def test_categories_returns_only_active_categories(self):
        response = self.api_client.get(reverse("api:catalog_categories"))

        assert response.status_code == 200
        names = [item["name"] for item in response.json()]
        assert "API数码" in names
        assert "API停用分类" not in names

    def test_public_listing_list_filters_active_listings(self):
        title_match = self.create_listing(
            title="专业蓝牙 耳机",
            description="支持降噪",
        )
        description_match = self.create_listing(
            title="普通键盘",
            description="支持蓝牙 耳机连接",
        )
        split_only = self.create_listing(
            title="蓝牙音箱",
            description="耳机配件",
        )
        self.create_listing(title="草稿商品", status=Listing.Status.DRAFT, published_at=None)
        self.create_listing(title="停用分类商品", category=self.inactive_category)

        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"q": " 蓝牙 耳机 "},
        )

        assert response.status_code == 200
        body = response.json()
        ids = [item["id"] for item in body["results"]]
        assert body["count"] == 2
        assert title_match.id in ids
        assert description_match.id in ids
        assert split_only.id not in ids
        assert body["results"][0]["category"]["name"] == "API数码"

    def test_public_listing_sort_aliases_use_stable_secondary_ordering(self):
        published_at = timezone.now() - timezone.timedelta(days=1)
        oldest = self.create_listing(
            title="最早的高价商品",
            price=Decimal("200.00"),
            published_at=published_at - timezone.timedelta(days=1),
        )
        first_same_value = self.create_listing(
            title="同值一号",
            price=Decimal("10.00"),
            published_at=published_at,
        )
        second_same_value = self.create_listing(
            title="同值二号",
            price=Decimal("10.00"),
            published_at=published_at,
        )
        url = reverse("api:catalog_listings")

        price_asc = self.api_client.get(url, {"sort": "price_asc"}).json()
        price_desc = self.api_client.get(url, {"sort": "price_desc"}).json()
        oldest_first = self.api_client.get(url, {"sort": "oldest"}).json()
        foreign_alias = self.api_client.get(url, {"sort": "updated_asc"}).json()

        assert [item["id"] for item in price_asc["results"]] == [
            first_same_value.id,
            second_same_value.id,
            oldest.id,
        ]
        assert [item["id"] for item in price_desc["results"]] == [
            oldest.id,
            second_same_value.id,
            first_same_value.id,
        ]
        assert [item["id"] for item in oldest_first["results"]] == [
            oldest.id,
            first_same_value.id,
            second_same_value.id,
        ]
        assert [item["id"] for item in foreign_alias["results"]] == [
            second_same_value.id,
            first_same_value.id,
            oldest.id,
        ]

    def test_public_detail_hides_inactive_or_non_active_listing(self):
        active = self.create_listing(title="详情商品")
        draft = self.create_listing(
            title="草稿详情",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        ok_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": active.id})
        )
        hidden_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": draft.id})
        )

        assert ok_response.status_code == 200
        assert ok_response.json()["title"] == "详情商品"
        assert hidden_response.status_code == 404

    def test_detail_returns_favorite_state_and_records_view_history(self):
        buyer = User.objects.create_user(
            username="favbuyer",
            email="favoritebuyer@example.com",
            password="StrongPass123",
        )
        listing = self.create_listing(title="收藏详情")
        ListingFavorite.objects.create(user=buyer, listing=listing)

        response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": listing.id}),
            **self.auth_headers(buyer),
        )

        assert response.status_code == 200
        assert response.json()["is_favorited"] is True
        assert ListingViewHistory.objects.filter(user=buyer, listing=listing).exists()

    def test_guest_detail_returns_not_favorited_and_does_not_record_history(self):
        listing = self.create_listing(title="游客详情")

        response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": listing.id})
        )

        assert response.status_code == 200
        assert response.json()["is_favorited"] is False
        assert ListingViewHistory.objects.count() == 0

    def test_paid_buyer_and_seller_can_view_reserved_or_sold_detail(self):
        buyer = User.objects.create_user(
            username="detailbuy",
            email="detail_buyer@example.com",
            password="StrongPass123",
        )
        reserved = self.create_listing(
            title="交易中详情",
            status=Listing.Status.RESERVED,
        )
        sold = self.create_listing(
            title="已售详情",
            status=Listing.Status.SOLD,
        )
        Order.objects.create(
            buyer=buyer,
            seller=self.seller,
            listing=reserved,
            buyer_display_name=buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=reserved.title,
            order_price=reserved.price,
            status=Order.OrderStatus.AWAITING_SHIPMENT,
            payment_deadline=timezone.now(),
        )
        Order.objects.create(
            buyer=buyer,
            seller=self.seller,
            listing=sold,
            buyer_display_name=buyer.username,
            seller_display_name=self.seller.username,
            listing_title_snapshot=sold.title,
            order_price=sold.price,
            status=Order.OrderStatus.COMPLETED,
            payment_deadline=timezone.now(),
        )

        buyer_reserved_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id}),
            **self.auth_headers(buyer),
        )
        seller_sold_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": sold.id}),
            **self.auth_headers(self.seller),
        )

        assert buyer_reserved_response.status_code == 200
        assert buyer_reserved_response.json()["title"] == "交易中详情"
        assert seller_sold_response.status_code == 200
        assert seller_sold_response.json()["title"] == "已售详情"

    def test_non_participant_cannot_view_reserved_or_sold_detail(self):
        reserved = self.create_listing(
            title="路人不可见",
            status=Listing.Status.RESERVED,
        )

        guest_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id})
        )
        other_response = self.api_client.get(
            reverse("api:catalog_listing_detail", kwargs={"pk": reserved.id}),
            **self.auth_headers(self.other_user),
        )

        assert guest_response.status_code == 404
        assert other_response.status_code == 404

    def test_owner_can_view_own_draft_listing_detail(self):
        draft = self.create_listing(
            title="编辑页草稿",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        response = self.api_client.get(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": draft.id}),
            **self.auth_headers(self.seller),
        )

        assert response.status_code == 200
        assert response.json()["id"] == draft.id
        assert response.json()["title"] == "编辑页草稿"
        assert response.json()["status"] == Listing.Status.DRAFT

    def test_non_owner_cannot_view_private_listing_detail(self):
        draft = self.create_listing(
            title="他人草稿",
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        response = self.api_client.get(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": draft.id}),
            **self.auth_headers(self.other_user),
        )

        assert response.status_code == 403

    def test_my_listing_list_filters_and_sorts_own_listings(self):
        target = self.create_listing(
            title="我的蓝牙耳机",
            description="轻微使用痕迹",
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
        )
        Listing.objects.filter(pk=target.pk).update(
            updated_at=timezone.now() - timezone.timedelta(days=2)
        )
        wrong_status = self.create_listing(
            title="我的蓝牙草稿",
            status=Listing.Status.DRAFT,
            price=Decimal("80.00"),
            published_at=None,
        )
        too_expensive = self.create_listing(
            title="我的蓝牙音箱",
            status=Listing.Status.ACTIVE,
            price=Decimal("188.00"),
        )
        other_owner = self.create_listing(
            owner=self.other_user,
            title="别人的蓝牙耳机",
            status=Listing.Status.ACTIVE,
            price=Decimal("88.00"),
        )
        sold = self.create_listing(
            title="已成交蓝牙耳机",
            status=Listing.Status.SOLD,
            price=Decimal("88.00"),
        )

        response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {
                "q": " 蓝牙 ",
                "status": Listing.Status.ACTIVE,
                "min_price": "50",
                "max_price": "100",
                "updated_after": (timezone.now() - timezone.timedelta(days=3)).isoformat(),
                "updated_before": (timezone.now() - timezone.timedelta(days=1)).isoformat(),
                "sort": "price_asc",
            },
            **self.auth_headers(self.seller),
        )

        ids = [item["id"] for item in response.json()["results"]]
        assert response.status_code == 200
        assert ids == [target.id]
        assert wrong_status.id not in ids
        assert too_expensive.id not in ids
        assert other_owner.id not in ids
        assert sold.id not in ids

    def test_my_listing_sort_aliases_use_stable_secondary_ordering(self):
        published_at = timezone.now() - timezone.timedelta(days=1)
        updated_at = timezone.now() - timezone.timedelta(hours=1)
        oldest = self.create_listing(
            title="最早更新的高价商品",
            price=Decimal("200.00"),
            published_at=published_at - timezone.timedelta(days=1),
        )
        first_same_value = self.create_listing(
            title="同值一号",
            price=Decimal("10.00"),
            published_at=published_at,
        )
        second_same_value = self.create_listing(
            title="同值二号",
            price=Decimal("10.00"),
            published_at=published_at,
        )
        Listing.objects.filter(pk=oldest.pk).update(
            updated_at=updated_at - timezone.timedelta(days=1)
        )
        Listing.objects.filter(
            pk__in=[first_same_value.pk, second_same_value.pk]
        ).update(updated_at=updated_at)
        url = reverse("api:catalog_my_listings")
        headers = self.auth_headers(self.seller)

        def result_ids(sort):
            response = self.api_client.get(url, {"sort": sort}, **headers)
            assert response.status_code == 200
            return [item["id"] for item in response.json()["results"]]

        assert result_ids("updated_asc") == [
            oldest.id,
            first_same_value.id,
            second_same_value.id,
        ]
        assert result_ids("published_desc") == [
            second_same_value.id,
            first_same_value.id,
            oldest.id,
        ]
        assert result_ids("published_asc") == [
            oldest.id,
            first_same_value.id,
            second_same_value.id,
        ]
        assert result_ids("price_asc") == [
            first_same_value.id,
            second_same_value.id,
            oldest.id,
        ]
        assert result_ids("price_desc") == [
            oldest.id,
            second_same_value.id,
            first_same_value.id,
        ]
        assert result_ids("oldest") == [
            second_same_value.id,
            first_same_value.id,
            oldest.id,
        ]

    def test_my_listing_list_excludes_sold_listing_and_rejects_sold_filter(self):
        """我的商品管理不展示已售出商品，也不接受已售出状态筛选。"""

        active = self.create_listing(title="可管理商品", status=Listing.Status.ACTIVE)
        sold = self.create_listing(title="已成交商品", status=Listing.Status.SOLD)

        list_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            **self.auth_headers(self.seller),
        )
        sold_filter_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {"status": Listing.Status.SOLD},
            **self.auth_headers(self.seller),
        )

        ids = [item["id"] for item in list_response.json()["results"]]
        assert list_response.status_code == 200
        assert active.id in ids
        assert sold.id not in ids
        assert sold_filter_response.status_code == 400

    def test_my_listing_list_invalid_filter_and_page_size_cap(self):
        for index in range(55):
            self.create_listing(title=f"我的分页商品{index}")

        invalid_price_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {"min_price": "100", "max_price": "10"},
            **self.auth_headers(self.seller),
        )
        invalid_time_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {
                "updated_after": "2026-05-02T10:00:00+08:00",
                "updated_before": "2026-05-01T10:00:00+08:00",
            },
            **self.auth_headers(self.seller),
        )
        page_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {"page_size": "999"},
            **self.auth_headers(self.seller),
        )
        keyword_response = self.api_client.get(
            reverse("api:catalog_my_listings"),
            {"q": "商" * 51},
            **self.auth_headers(self.seller),
        )

        assert invalid_price_response.status_code == 400
        assert "最高价格不得低于最低价格" in invalid_price_response.json()["message"]
        assert invalid_time_response.status_code == 400
        assert "更新时间截止不得早于更新时间起始" in invalid_time_response.json()["message"]
        assert keyword_response.status_code == 400
        assert "搜索关键词不能超过50个字符" in keyword_response.json()["message"]
        assert "q" in keyword_response.json()["errors"]
        assert page_response.status_code == 200
        assert page_response.json()["page_size"] == 50
        assert len(page_response.json()["results"]) == 50

    def test_create_update_publish_deactivate_and_reactivate_listing(self):
        create_response = self.api_client.post(
            reverse("api:catalog_my_listings"),
            data=self.listing_payload(),
            format="json",
            **self.auth_headers(self.seller),
        )
        assert create_response.status_code == 201
        listing_id = create_response.json()["id"]
        assert create_response.json()["status"] == Listing.Status.DRAFT

        update_response = self.api_client.patch(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": listing_id}),
            data={"title": "更新后的相机", "price": "399.00"},
            format="json",
            **self.auth_headers(self.seller),
        )
        assert update_response.status_code == 200
        assert update_response.json()["title"] == "更新后的相机"

        publish_response = self.api_client.post(
            reverse("api:catalog_my_listing_publish", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        assert publish_response.status_code == 200
        assert publish_response.json()["status"] == Listing.Status.ACTIVE

        deactivate_response = self.api_client.post(
            reverse("api:catalog_my_listing_deactivate", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        assert deactivate_response.status_code == 200
        assert deactivate_response.json()["status"] == Listing.Status.WITHDRAWN

        reactivate_response = self.api_client.post(
            reverse("api:catalog_my_listing_reactivate", kwargs={"pk": listing_id}),
            **self.auth_headers(self.seller),
        )
        assert reactivate_response.status_code == 200
        assert reactivate_response.json()["status"] == Listing.Status.ACTIVE

    def test_non_owner_cannot_mutate_listing(self):
        listing = self.create_listing()

        response = self.api_client.patch(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": listing.id}),
            data={"title": "越权修改"},
            format="json",
            **self.auth_headers(self.other_user),
        )

        assert response.status_code == 403
        listing.refresh_from_db()
        assert listing.title != "越权修改"

    def test_my_listing_detail_does_not_enable_put_during_generic_view_migration(self):
        """详情接口保持原有 GET/PATCH/DELETE 方法边界。"""

        listing = self.create_listing(status=Listing.Status.DRAFT, published_at=None)

        response = self.api_client.put(
            reverse("api:catalog_my_listing_detail", kwargs={"pk": listing.id}),
            data={"title": "不应通过 PUT 更新"},
            format="json",
            **self.auth_headers(self.seller),
        )

        assert response.status_code == 405
        listing.refresh_from_db()
        assert listing.title != "不应通过 PUT 更新"

    def test_image_upload_reorder_delete_and_limit(self):
        listing = self.create_listing(status=Listing.Status.DRAFT, published_at=None)

        upload_response = self.api_client.post(
            reverse("api:catalog_my_listing_images_upload", kwargs={"pk": listing.id}),
            data={
                "images": [
                    build_png_image("first.png"),
                    build_png_image("second.png"),
                ]
            },
            format="multipart",
            **self.auth_headers(self.seller),
        )
        assert upload_response.status_code == 201
        image_ids = [image["id"] for image in upload_response.json()["images"]]
        assert len(image_ids) == 2

        reorder_response = self.api_client.post(
            reverse("api:catalog_my_listing_images_reorder", kwargs={"pk": listing.id}),
            data={"image_ids": list(reversed(image_ids))},
            format="json",
            **self.auth_headers(self.seller),
        )
        assert reorder_response.status_code == 200
        assert [image["id"] for image in reorder_response.json()["images"]] == list(
            reversed(image_ids)
        )

        delete_response = self.api_client.delete(
            reverse(
                "api:catalog_my_listing_images_delete",
                kwargs={"pk": listing.id, "image_id": image_ids[0]},
            ),
            **self.auth_headers(self.seller),
        )
        assert delete_response.status_code == 204
        assert ListingImage.objects.filter(pk=image_ids[0]).exists() is False

        too_many_response = self.api_client.post(
            reverse("api:catalog_my_listing_images_upload", kwargs={"pk": listing.id}),
            data={"images": [build_png_image(f"extra-{index}.png") for index in range(6)]},
            format="multipart",
            **self.auth_headers(self.seller),
        )
        assert too_many_response.status_code == 400

    def test_invalid_filter_returns_json_error(self):
        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"min_price": "100", "max_price": "10"},
        )

        assert response.status_code == 400
        assert "message" in response.json()
        assert "最高价格不得低于最低价格" in response.json()["message"]

    def test_invalid_published_range_returns_json_error(self):
        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {
                "published_after": "2026-05-02T10:00",
                "published_before": "2026-05-01T10:00",
            },
        )

        assert response.status_code == 400
        assert "发布时间截止不得早于发布时间起始" in response.json()["message"]

    def test_public_listing_list_supports_published_range_filter(self):
        old = self.create_listing(
            title="较早发布",
            published_at=timezone.now() - timezone.timedelta(days=5),
        )
        target = self.create_listing(
            title="区间发布",
            published_at=timezone.now() - timezone.timedelta(days=2),
        )
        new = self.create_listing(title="最新发布", published_at=timezone.now())

        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {
                "published_after": (timezone.now() - timezone.timedelta(days=3)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                "published_before": (timezone.now() - timezone.timedelta(days=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            },
        )

        ids = [item["id"] for item in response.json()["results"]]
        assert response.status_code == 200
        assert target.id in ids
        assert old.id not in ids
        assert new.id not in ids

    def test_blank_and_too_long_keyword_handling(self):
        first = self.create_listing(title="蓝牙耳机")
        second = self.create_listing(title="普通键盘")

        blank_response = self.api_client.get(reverse("api:catalog_listings"), {"q": "   "})
        long_response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"q": "蓝" * 51},
        )

        ids = [item["id"] for item in blank_response.json()["results"]]
        assert blank_response.status_code == 200
        assert first.id in ids
        assert second.id in ids
        assert long_response.status_code == 400
        assert "搜索关键词不能超过50个字符" in long_response.json()["message"]
        assert "q" in long_response.json()["errors"]

    def test_public_listing_page_size_is_capped_at_50(self):
        for index in range(55):
            self.create_listing(title=f"分页商品{index}")

        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"page_size": "999"},
        )

        body = response.json()
        assert response.status_code == 200
        assert body["page_size"] == 50
        assert len(body["results"]) == 50

    def test_public_listing_empty_result_uses_first_page_for_out_of_range_page(self):
        """空列表请求超出范围页码时仍返回稳定的第一页空结果。"""

        response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"page": "999"},
        )

        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 0
        assert body["results"] == []
        assert body["next"] is None
        assert body["previous"] is None

    def test_public_listing_page_number_is_limited_to_valid_range(self):
        """负数页码回退首页，超出范围页码定位到最后一页。"""

        for index in range(21):
            self.create_listing(title=f"页码边界商品{index}")

        first_page_response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"page": "1", "page_size": "20"},
        )
        negative_page_response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"page": "-1", "page_size": "20"},
        )
        overflow_page_response = self.api_client.get(
            reverse("api:catalog_listings"),
            {"page": "999", "page_size": "20"},
        )

        first_page = first_page_response.json()
        negative_page = negative_page_response.json()
        overflow_page = overflow_page_response.json()
        assert first_page_response.status_code == 200
        assert negative_page_response.status_code == 200
        assert overflow_page_response.status_code == 200
        assert negative_page["results"] == first_page["results"]
        assert len(overflow_page["results"]) == 1
        assert overflow_page["next"] is None
        assert "page=1" in overflow_page["previous"]

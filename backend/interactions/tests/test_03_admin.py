"""interactions 应用 pytest 测试。"""

from decimal import Decimal

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Listing
from interactions.admin import CommentAdmin, ReplyStatusFilter
from interactions.models import Comment
from interactions.selectors import get_listing_comments


pytestmark = pytest.mark.django_db
User = get_user_model()

@pytest.fixture
def comment_context():
    """为留言测试创建稳定的用户、分类和商品数据。"""

    seller = User.objects.create_user(
        username="留言卖家",
        email="comment-seller@example.com",
        password="StrongPass123",
    )
    buyer = User.objects.create_user(
        username="留言买家",
        email="comment-buyer@example.com",
        password="StrongPass123",
    )
    other_user = User.objects.create_user(
        username="留言路人",
        email="comment-other@example.com",
        password="StrongPass123",
    )
    category = Category.objects.create(name="留言分类")
    seller.profile.nickname = "公开卖家昵称"
    seller.profile.save(update_fields=["nickname", "updated_at"])
    buyer.profile.nickname = "公开买家昵称"
    buyer.profile.save(update_fields=["nickname", "updated_at"])

    def create_listing(**overrides):
        data = {
            "owner": seller,
            "category": category,
            "title": "留言商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": Decimal("88.00"),
            "condition": Listing.Condition.GOOD,
            "description": "商品详情描述",
            "delivery_notes": "地铁站面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    listing = create_listing(title="留言商品")
    other_listing = create_listing(title="其他留言商品")
    return {
        "seller": seller,
        "buyer": buyer,
        "other_user": other_user,
        "category": category,
        "listing": listing,
        "other_listing": other_listing,
        "create_listing": create_listing,
    }



class TestCommentAdmin:
    """留言后台基础配置、回复筛选和访问烟雾测试。"""

    def test_comment_registered_to_admin_site(self):
        assert isinstance(site._registry[Comment], CommentAdmin)

    def test_comment_admin_exposes_required_columns_filters_search_and_readonly_fields(self):
        comment_admin = site._registry[Comment]

        for field in [
            "author",
            "listing",
            "parent",
            "is_reply",
            "short_content",
            "created_at",
            "updated_at",
        ]:
            assert field in comment_admin.list_display

        assert "author" in comment_admin.list_filter
        assert ReplyStatusFilter in comment_admin.list_filter
        assert "created_at" in comment_admin.list_filter
        assert "listing" in comment_admin.list_filter

        for field in ["content", "listing__title", "author__username"]:
            assert field in comment_admin.search_fields

        for field in ["author", "listing", "parent", "created_at", "updated_at"]:
            assert field in comment_admin.readonly_fields

        assert comment_admin.list_select_related == ["author", "listing", "parent"]

    def test_comment_admin_summary_and_reply_marker_use_existing_comment_fields(self, comment_context):
        comment_admin = site._registry[Comment]
        parent = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["buyer"],
            content="这是一段超过二十个字符的留言内容用于验证摘要截断",
        )
        reply = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["seller"],
            parent=parent,
            content="回复内容",
        )

        assert comment_admin.short_content(parent) == parent.content[0:20]
        assert comment_admin.is_reply(parent) is False
        assert comment_admin.is_reply(reply) is True

    def test_reply_status_filter_limits_top_level_comments_and_replies(self, comment_context):
        comment_admin = site._registry[Comment]
        parent = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["buyer"],
            content="顶层留言",
        )
        reply = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["seller"],
            parent=parent,
            content="二级回复",
        )

        reply_filter = ReplyStatusFilter(None, {"is_reply": ["yes"]}, Comment, comment_admin)
        top_level_filter = ReplyStatusFilter(None, {"is_reply": ["no"]}, Comment, comment_admin)

        assert list(reply_filter.queryset(None, Comment.objects.order_by("id"))) == [reply]
        assert list(top_level_filter.queryset(None, Comment.objects.order_by("id"))) == [parent]

    def test_superuser_can_open_comment_admin_changelist(self, client):
        superuser = User.objects.create_superuser(
            username="cmtadmin",
            email="commentadmin@example.com",
            password="StrongPass123",
        )
        client.force_login(superuser)

        response = client.get(reverse("admin:interactions_comment_changelist"))

        assert response.status_code == 200

    def test_regular_user_cannot_open_comment_admin_changelist(self, client, comment_context):
        client.force_login(comment_context["buyer"])

        response = client.get(reverse("admin:interactions_comment_changelist"))

        assert response.status_code in [302, 403]



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



class TestCommentModel:
    """留言模型基础行为测试。"""

    def test_comment_links_to_listing_and_keeps_stable_order(self, comment_context):
        listing = comment_context["listing"]
        buyer = comment_context["buyer"]
        seller = comment_context["seller"]
        first = Comment.objects.create(listing=listing, author=buyer, content="第一条留言")
        second = Comment.objects.create(listing=listing, author=seller, content="第二条留言")

        comments = list(Comment.objects.filter(listing=listing))

        assert comments == [first, second]
        assert isinstance(first.listing, Listing)

    def test_comment_author_can_be_null(self, comment_context):
        other_user = comment_context["other_user"]
        comment = Comment.objects.create(
            listing=comment_context["listing"],
            author=other_user,
            content="作者后续会注销",
        )

        other_user.delete()
        comment.refresh_from_db()

        assert comment.author is None
        assert comment.content == "作者后续会注销"

    def test_reply_links_to_parent_listing_and_author(self, comment_context):
        listing = comment_context["listing"]
        buyer = comment_context["buyer"]
        seller = comment_context["seller"]
        parent = Comment.objects.create(listing=listing, author=buyer, content="顶层留言")
        reply = Comment.objects.create(
            listing=listing,
            author=seller,
            parent=parent,
            content="二级回复",
        )

        assert reply.parent == parent
        assert reply.listing == listing
        assert reply.author == seller

    def test_str_truncates_long_content(self, comment_context):
        comment = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["buyer"],
            content="这是一条非常长的留言内容，用于确认后台和日志中不会输出完整正文。",
        )

        assert str(comment) == comment.content[:20]



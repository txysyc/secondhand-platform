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



class TestCommentSelector:
    """留言读取查询测试。"""

    def test_get_listing_comments_returns_only_target_listing_comments(self, comment_context):
        listing = comment_context["listing"]
        buyer = comment_context["buyer"]
        seller = comment_context["seller"]
        target = Comment.objects.create(listing=listing, author=buyer, content="目标商品留言")
        Comment.objects.create(listing=listing, author=seller, parent=target, content="目标商品回复")
        Comment.objects.create(
            listing=comment_context["other_listing"],
            author=buyer,
            content="其他商品留言",
        )

        comments = list(get_listing_comments(listing))

        assert comments == [target]

    def test_get_listing_comments_selects_author_and_profile(self, comment_context, django_assert_num_queries):
        Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["buyer"],
            content="需要展示作者资料",
        )
        comments = list(get_listing_comments(comment_context["listing"]))

        with django_assert_num_queries(0):
            assert comments[0].author.profile.nickname == "公开买家昵称"

    def test_get_listing_comments_prefetches_reply_author_and_profile(self, comment_context, django_assert_num_queries):
        parent = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["buyer"],
            content="顶层留言",
        )
        Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["seller"],
            parent=parent,
            content="卖家回复",
        )

        comments = list(get_listing_comments(comment_context["listing"]))

        with django_assert_num_queries(0):
            reply = comments[0].replies.all()[0]
            assert reply.author.profile.nickname == "公开卖家昵称"

    def test_get_listing_comments_ignores_cross_listing_dirty_reply(self, comment_context):
        parent = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["buyer"],
            content="目标商品顶层留言",
        )
        valid_reply = Comment.objects.create(
            listing=comment_context["listing"],
            author=comment_context["seller"],
            parent=parent,
            content="同商品回复",
        )
        Comment.objects.create(
            listing=comment_context["other_listing"],
            author=comment_context["seller"],
            parent=parent,
            content="跨商品脏回复",
        )

        comments = list(get_listing_comments(comment_context["listing"]))

        assert list(comments[0].replies.all()) == [valid_reply]

    def test_get_listing_comments_orders_top_level_and_replies_stably(self, comment_context):
        listing = comment_context["listing"]
        buyer = comment_context["buyer"]
        seller = comment_context["seller"]
        first = Comment.objects.create(listing=listing, author=buyer, content="第一条顶层留言")
        second = Comment.objects.create(listing=listing, author=buyer, content="第二条顶层留言")
        first_reply = Comment.objects.create(
            listing=listing,
            author=seller,
            parent=first,
            content="第一条回复",
        )
        second_reply = Comment.objects.create(
            listing=listing,
            author=seller,
            parent=first,
            content="第二条回复",
        )

        comments = list(get_listing_comments(listing))

        assert comments == [first, second]
        assert list(comments[0].replies.all()) == [first_reply, second_reply]



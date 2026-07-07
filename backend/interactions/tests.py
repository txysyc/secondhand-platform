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


@pytest.fixture
def interactions_api_context():
    """构造评论 API 测试数据和快捷创建函数。"""

    seller = User.objects.create_user(
        username="cmt_seller",
        email="comment_seller@example.com",
        password="StrongPass123",
    )
    buyer = User.objects.create_user(
        username="cmt_buyer",
        email="comment_buyer@example.com",
        password="StrongPass123",
    )
    other = User.objects.create_user(
        username="cmt_other",
        email="comment_other@example.com",
        password="StrongPass123",
    )
    category = Category.objects.create(name="评论分类")
    inactive_category = Category.objects.create(name="评论停用分类", is_active=False)

    def create_listing(**overrides):
        data = {
            "owner": seller,
            "category": category,
            "title": "评论商品",
            "item_type": Listing.ItemType.PHYSICAL,
            "status": Listing.Status.ACTIVE,
            "price": "99.00",
            "condition": Listing.Condition.GOOD,
            "description": "评论描述",
            "delivery_notes": "面交",
            "physical_delivery_method": Listing.PhysicalDeliveryMethod.MEETUP,
            "published_at": timezone.now(),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    listing = create_listing()

    def create_comment(**overrides):
        data = {
            "listing": listing,
            "author": buyer,
            "content": "顶层留言",
        }
        data.update(overrides)
        return Comment.objects.create(**data)

    return {
        "seller": seller,
        "buyer": buyer,
        "other": other,
        "category": category,
        "inactive_category": inactive_category,
        "listing": listing,
        "create_listing": create_listing,
        "create_comment": create_comment,
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


class TestInteractionsApi:
    """评论互动 API 测试。"""

    def test_get_comments_returns_nested_replies(self, api_client, interactions_api_context):
        parent = interactions_api_context["create_comment"]()
        reply = Comment.objects.create(
            listing=interactions_api_context["listing"],
            author=interactions_api_context["seller"],
            parent=parent,
            content="卖家回复",
        )

        response = api_client.get(
            reverse(
                "api:listing_comments",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            )
        )

        assert response.status_code == 200
        body = response.json()
        assert body[0]["id"] == parent.id
        assert body[0]["replies"][0]["id"] == reply.id
        assert body[0]["author"]["username"] == interactions_api_context["buyer"].username

    def test_guest_can_view_comments_for_active_listing(self, api_client, interactions_api_context):
        interactions_api_context["create_comment"]()

        response = api_client.get(
            reverse(
                "api:listing_comments",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            )
        )

        assert response.status_code == 200
        assert response.json()[0]["content"] == "顶层留言"

    def test_create_comment_requires_login(self, api_client, interactions_api_context):
        response = api_client.post(
            reverse(
                "api:listing_comments",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            data={"content": "游客留言"},
            format="json",
        )

        assert response.status_code == 401

    def test_create_comment_for_active_listing_succeeds(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        response = api_client.post(
            reverse(
                "api:listing_comments",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            data={"content": "请问还在吗？"},
            format="json",
            **auth_headers(interactions_api_context["buyer"]),
        )

        assert response.status_code == 201
        assert response.json()["content"] == "请问还在吗？"
        assert Comment.objects.count() == 1

    def test_create_comment_rejects_blank_and_non_interactive_listing(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        reserved = interactions_api_context["create_listing"](status=Listing.Status.RESERVED)

        blank_response = api_client.post(
            reverse(
                "api:listing_comments",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            data={"content": "   "},
            format="json",
            **auth_headers(interactions_api_context["buyer"]),
        )
        reserved_response = api_client.post(
            reverse("api:listing_comments", kwargs={"listing_id": reserved.id}),
            data={"content": "还能留言吗"},
            format="json",
            **auth_headers(interactions_api_context["seller"]),
        )

        assert blank_response.status_code == 400
        assert blank_response.json()["message"] == "留言内容不能为空"
        assert reserved_response.status_code == 400
        assert reserved_response.json()["message"] == "该商品目前不能发表评论"

    def test_reply_requires_login_and_rejects_nested_reply(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        parent = interactions_api_context["create_comment"]()
        nested = Comment.objects.create(
            listing=interactions_api_context["listing"],
            author=interactions_api_context["seller"],
            parent=parent,
            content="二级回复",
        )

        guest_response = api_client.post(
            reverse("api:comment_replies", kwargs={"comment_id": parent.id}),
            data={"content": "游客回复"},
            format="json",
        )
        nested_response = api_client.post(
            reverse("api:comment_replies", kwargs={"comment_id": nested.id}),
            data={"content": "三级回复"},
            format="json",
            **auth_headers(interactions_api_context["other"]),
        )

        assert guest_response.status_code == 401
        assert nested_response.status_code == 400
        assert nested_response.json()["message"] == "不得创建多级留言"

    def test_reply_to_top_level_comment_succeeds(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        parent = interactions_api_context["create_comment"]()

        response = api_client.post(
            reverse("api:comment_replies", kwargs={"comment_id": parent.id}),
            data={"content": "可以面交吗？"},
            format="json",
            **auth_headers(interactions_api_context["seller"]),
        )

        assert response.status_code == 201
        assert response.json()["parent_id"] == parent.id
        assert Comment.objects.filter(parent=parent).count() == 1

    def test_delete_comment_requires_author_and_supports_owner_only(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        comment = interactions_api_context["create_comment"](
            author=interactions_api_context["buyer"]
        )

        other_response = api_client.delete(
            reverse("api:comment_detail", kwargs={"comment_id": comment.id}),
            **auth_headers(interactions_api_context["other"]),
        )
        author_response = api_client.delete(
            reverse("api:comment_detail", kwargs={"comment_id": comment.id}),
            **auth_headers(interactions_api_context["buyer"]),
        )

        assert other_response.status_code == 403
        assert author_response.status_code == 204
        assert Comment.objects.filter(pk=comment.pk).exists() is False

    def test_delete_top_level_comment_cascades_reply(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        parent = interactions_api_context["create_comment"](
            author=interactions_api_context["buyer"]
        )
        reply = Comment.objects.create(
            listing=interactions_api_context["listing"],
            author=interactions_api_context["seller"],
            parent=parent,
            content="回复内容",
        )

        response = api_client.delete(
            reverse("api:comment_detail", kwargs={"comment_id": parent.id}),
            **auth_headers(interactions_api_context["buyer"]),
        )

        assert response.status_code == 204
        assert Comment.objects.filter(pk=parent.pk).exists() is False
        assert Comment.objects.filter(pk=reply.pk).exists() is False

    def test_inactive_category_listing_comments_are_hidden(
        self,
        api_client,
        interactions_api_context,
    ):
        hidden = interactions_api_context["create_listing"](
            category=interactions_api_context["inactive_category"],
            status=Listing.Status.ACTIVE,
        )

        response = api_client.get(
            reverse("api:listing_comments", kwargs={"listing_id": hidden.id})
        )

        assert response.status_code == 404

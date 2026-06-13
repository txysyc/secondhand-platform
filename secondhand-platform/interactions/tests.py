from decimal import Decimal

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.models import Category, Listing
from interactions.admin import CommentAdmin, ReplyStatusFilter
from interactions.models import Comment
from interactions.selectors import get_listing_comments


User = get_user_model()


class CommentTestMixin:
    """为留言测试创建稳定的用户、分类和商品数据。"""

    @classmethod
    def setUpTestData(cls):
        cls.seller = User.objects.create_user(
            username="留言卖家",
            email="comment-seller@example.com",
            password="StrongPass123",
        )
        cls.buyer = User.objects.create_user(
            username="留言买家",
            email="comment-buyer@example.com",
            password="StrongPass123",
        )
        cls.other_user = User.objects.create_user(
            username="留言路人",
            email="comment-other@example.com",
            password="StrongPass123",
        )
        cls.category = Category.objects.create(name="留言分类")
        cls.listing = cls.create_listing(title="留言商品")
        cls.other_listing = cls.create_listing(title="其他留言商品")
        cls.seller.profile.nickname = "公开卖家昵称"
        cls.seller.profile.save(update_fields=["nickname", "updated_at"])
        cls.buyer.profile.nickname = "公开买家昵称"
        cls.buyer.profile.save(update_fields=["nickname", "updated_at"])

    @classmethod
    def create_listing(cls, **overrides):
        data = {
            "owner": cls.seller,
            "category": cls.category,
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


class CommentModelTest(CommentTestMixin, TestCase):
    """留言模型基础行为测试。"""

    def test_comment_links_to_listing_and_keeps_stable_order(self):
        first = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="第一条留言",
        )
        second = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="第二条留言",
        )

        comments = list(Comment.objects.filter(listing=self.listing))

        self.assertEqual(comments, [first, second])
        self.assertIsInstance(first.listing, Listing)

    def test_comment_author_can_be_null(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.other_user,
            content="作者后续会注销",
        )

        self.other_user.delete()
        comment.refresh_from_db()

        self.assertIsNone(comment.author)
        self.assertEqual(comment.content, "作者后续会注销")

    def test_reply_links_to_parent_listing_and_author(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="顶层留言",
        )
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="二级回复",
        )

        self.assertEqual(reply.parent, parent)
        self.assertEqual(reply.listing, self.listing)
        self.assertEqual(reply.author, self.seller)

    def test_str_truncates_long_content(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="这是一条非常长的留言内容，用于确认后台和日志中不会输出完整正文。",
        )

        self.assertEqual(str(comment), comment.content[:20])


class CommentSelectorTest(CommentTestMixin, TestCase):
    """留言读取查询测试。"""

    def test_get_listing_comments_returns_only_target_listing_comments(self):
        target = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="目标商品留言",
        )
        Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=target,
            content="目标商品回复",
        )
        Comment.objects.create(
            listing=self.other_listing,
            author=self.buyer,
            content="其他商品留言",
        )

        comments = list(get_listing_comments(self.listing))

        self.assertEqual(comments, [target])

    def test_get_listing_comments_selects_author_and_profile(self):
        Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="需要展示作者资料",
        )
        comments = list(get_listing_comments(self.listing))

        with self.assertNumQueries(0):
            self.assertEqual(comments[0].author.profile.nickname, "公开买家昵称")

    def test_get_listing_comments_prefetches_reply_author_and_profile(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="顶层留言",
        )
        Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="卖家回复",
        )

        comments = list(get_listing_comments(self.listing))

        with self.assertNumQueries(0):
            reply = comments[0].replies.all()[0]
            self.assertEqual(reply.author.profile.nickname, "公开卖家昵称")

    def test_get_listing_comments_ignores_cross_listing_dirty_reply(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="目标商品顶层留言",
        )
        valid_reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="同商品回复",
        )
        Comment.objects.create(
            listing=self.other_listing,
            author=self.seller,
            parent=parent,
            content="跨商品脏回复",
        )

        comments = list(get_listing_comments(self.listing))

        self.assertEqual(list(comments[0].replies.all()), [valid_reply])

    def test_get_listing_comments_orders_top_level_and_replies_stably(self):
        first = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="第一条顶层留言",
        )
        second = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="第二条顶层留言",
        )
        first_reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=first,
            content="第一条回复",
        )
        second_reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=first,
            content="第二条回复",
        )

        comments = list(get_listing_comments(self.listing))

        self.assertEqual(comments, [first, second])
        self.assertEqual(list(comments[0].replies.all()), [first_reply, second_reply])


class CommentAdminTest(CommentTestMixin, TestCase):
    """留言后台基础配置、回复筛选和访问烟雾测试。"""

    def test_comment_registered_to_admin_site(self):
        self.assertIsInstance(site._registry[Comment], CommentAdmin)

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
            self.assertIn(field, comment_admin.list_display)

        self.assertIn("author", comment_admin.list_filter)
        self.assertIn(ReplyStatusFilter, comment_admin.list_filter)
        self.assertIn("created_at", comment_admin.list_filter)
        self.assertIn("listing", comment_admin.list_filter)

        for field in ["content", "listing__title", "author__username"]:
            self.assertIn(field, comment_admin.search_fields)

        for field in ["author", "listing", "parent", "created_at", "updated_at"]:
            self.assertIn(field, comment_admin.readonly_fields)

        self.assertEqual(comment_admin.list_select_related, ["author", "listing", "parent"])

    def test_comment_admin_summary_and_reply_marker_use_existing_comment_fields(self):
        comment_admin = site._registry[Comment]
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="这是一段超过二十个字符的留言内容用于验证摘要截断",
        )
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="回复内容",
        )

        self.assertEqual(comment_admin.short_content(parent), parent.content[0:20])
        self.assertFalse(comment_admin.is_reply(parent))
        self.assertTrue(comment_admin.is_reply(reply))

    def test_reply_status_filter_limits_top_level_comments_and_replies(self):
        comment_admin = site._registry[Comment]
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="顶层留言",
        )
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="二级回复",
        )

        reply_filter = ReplyStatusFilter(
            None,
            {"is_reply": ["yes"]},
            Comment,
            comment_admin,
        )
        top_level_filter = ReplyStatusFilter(
            None,
            {"is_reply": ["no"]},
            Comment,
            comment_admin,
        )

        self.assertQuerySetEqual(
            reply_filter.queryset(None, Comment.objects.order_by("id")),
            [reply],
        )
        self.assertQuerySetEqual(
            top_level_filter.queryset(None, Comment.objects.order_by("id")),
            [parent],
        )

    def test_superuser_can_open_comment_admin_changelist(self):
        superuser = User.objects.create_superuser(
            username="cmtadmin",
            email="commentadmin@example.com",
            password="StrongPass123",
        )
        self.client.force_login(superuser)

        response = self.client.get(reverse("admin:interactions_comment_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_open_comment_admin_changelist(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("admin:interactions_comment_changelist"))

        self.assertIn(response.status_code, [302, 403])




class InteractionsApiTests(APITestCase):
    """P4 评论互动 API 测试。"""

    def setUp(self):
        self.client = APIClient()
        self.seller = User.objects.create_user(
            username="cmt_seller",
            email="comment_seller@example.com",
            password="StrongPass123",
        )
        self.buyer = User.objects.create_user(
            username="cmt_buyer",
            email="comment_buyer@example.com",
            password="StrongPass123",
        )
        self.other = User.objects.create_user(
            username="cmt_other",
            email="comment_other@example.com",
            password="StrongPass123",
        )
        self.category = Category.objects.create(name="评论分类")
        self.inactive_category = Category.objects.create(
            name="评论停用分类",
            is_active=False,
        )
        self.listing = self.create_listing()

    def auth_headers(self, user):
        token = RefreshToken.for_user(user).access_token
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def create_listing(self, **overrides):
        data = {
            "owner": self.seller,
            "category": self.category,
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

    def create_comment(self, **overrides):
        data = {
            "listing": self.listing,
            "author": self.buyer,
            "content": "顶层留言",
        }
        data.update(overrides)
        return Comment.objects.create(**data)

    def test_get_comments_returns_nested_replies(self):
        parent = self.create_comment()
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="卖家回复",
        )

        response = self.client.get(
            reverse("api:listing_comments", kwargs={"listing_id": self.listing.id})
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["id"], parent.id)
        self.assertEqual(body[0]["replies"][0]["id"], reply.id)
        self.assertEqual(body[0]["author"]["username"], self.buyer.username)

    def test_guest_can_view_comments_for_active_listing(self):
        self.create_comment()

        response = self.client.get(
            reverse("api:listing_comments", kwargs={"listing_id": self.listing.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["content"], "顶层留言")

    def test_create_comment_requires_login(self):
        response = self.client.post(
            reverse("api:listing_comments", kwargs={"listing_id": self.listing.id}),
            data={"content": "游客留言"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_create_comment_for_active_listing_succeeds(self):
        response = self.client.post(
            reverse("api:listing_comments", kwargs={"listing_id": self.listing.id}),
            data={"content": "请问还在吗？"},
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["content"], "请问还在吗？")
        self.assertEqual(Comment.objects.count(), 1)

    def test_create_comment_rejects_blank_and_non_interactive_listing(self):
        reserved = self.create_listing(status=Listing.Status.RESERVED)

        blank_response = self.client.post(
            reverse("api:listing_comments", kwargs={"listing_id": self.listing.id}),
            data={"content": "   "},
            format="json",
            **self.auth_headers(self.buyer),
        )
        reserved_response = self.client.post(
            reverse("api:listing_comments", kwargs={"listing_id": reserved.id}),
            data={"content": "还能留言吗"},
            format="json",
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(blank_response.status_code, 400)
        self.assertEqual(blank_response.json()["message"], "留言内容不能为空")
        self.assertEqual(reserved_response.status_code, 400)
        self.assertEqual(reserved_response.json()["message"], "该商品目前不能发表评论")

    def test_reply_requires_login_and_rejects_nested_reply(self):
        parent = self.create_comment()
        nested = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="二级回复",
        )

        guest_response = self.client.post(
            reverse("api:comment_replies", kwargs={"comment_id": parent.id}),
            data={"content": "游客回复"},
            format="json",
        )
        nested_response = self.client.post(
            reverse("api:comment_replies", kwargs={"comment_id": nested.id}),
            data={"content": "三级回复"},
            format="json",
            **self.auth_headers(self.other),
        )

        self.assertEqual(guest_response.status_code, 401)
        self.assertEqual(nested_response.status_code, 400)
        self.assertEqual(nested_response.json()["message"], "不得创建多级留言")

    def test_reply_to_top_level_comment_succeeds(self):
        parent = self.create_comment()

        response = self.client.post(
            reverse("api:comment_replies", kwargs={"comment_id": parent.id}),
            data={"content": "可以面交吗？"},
            format="json",
            **self.auth_headers(self.seller),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent_id"], parent.id)
        self.assertEqual(Comment.objects.filter(parent=parent).count(), 1)

    def test_delete_comment_requires_author_and_supports_owner_only(self):
        comment = self.create_comment(author=self.buyer)

        other_response = self.client.delete(
            reverse("api:comment_detail", kwargs={"comment_id": comment.id}),
            **self.auth_headers(self.other),
        )
        author_response = self.client.delete(
            reverse("api:comment_detail", kwargs={"comment_id": comment.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(other_response.status_code, 403)
        self.assertEqual(author_response.status_code, 204)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())

    def test_delete_top_level_comment_cascades_reply(self):
        parent = self.create_comment(author=self.buyer)
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="回复内容",
        )

        response = self.client.delete(
            reverse("api:comment_detail", kwargs={"comment_id": parent.id}),
            **self.auth_headers(self.buyer),
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Comment.objects.filter(pk=parent.pk).exists())
        self.assertFalse(Comment.objects.filter(pk=reply.pk).exists())

    def test_inactive_category_listing_comments_are_hidden(self):
        hidden = self.create_listing(
            category=self.inactive_category,
            status=Listing.Status.ACTIVE,
        )

        response = self.client.get(
            reverse("api:listing_comments", kwargs={"listing_id": hidden.id})
        )

        self.assertEqual(response.status_code, 404)

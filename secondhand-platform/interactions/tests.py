from decimal import Decimal

from django.contrib.admin.sites import site
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Listing
from interactions.admin import CommentAdmin
from interactions.models import Comment
from interactions.selectors import get_listing_comments
from interactions.services import create_comment, create_reply


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


class CommentAdminTest(TestCase):
    """留言后台基础配置测试。"""

    def test_comment_registered_to_admin_site(self):
        self.assertIsInstance(site._registry[Comment], CommentAdmin)

    def test_comment_admin_exposes_required_columns_filters_and_search(self):
        comment_admin = site._registry[Comment]

        for field in ["listing", "author", "short_content", "created_at"]:
            self.assertIn(field, comment_admin.list_display)
        self.assertIn("created_at", comment_admin.list_filter)
        self.assertIn("content", comment_admin.search_fields)
        self.assertIn("listing__title", comment_admin.search_fields)
        self.assertIn("author__username", comment_admin.search_fields)


class ListingCommentThreadViewTest(CommentTestMixin, TestCase):
    """商品详情页留言线程展示测试。"""

    def detail_url(self, listing=None):
        listing = listing or self.listing
        return reverse("catalog:listing_detail", kwargs={"pk": listing.pk})

    def test_detail_page_shows_comment_author_time_content_and_seller_badge(self):
        buyer_comment = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="请问还能面交吗？",
        )
        seller_comment = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="可以，工作日晚上方便。",
        )

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "interactions/comment_thread.html")
        self.assertContains(response, "公开留言")
        self.assertContains(response, "公开买家昵称")
        self.assertContains(response, "请问还能面交吗？")
        self.assertContains(response, "公开卖家昵称")
        self.assertContains(response, "可以，工作日晚上方便。")
        self.assertContains(response, "卖家")
        self.assertContains(response, buyer_comment.created_at.strftime("%Y-%m-%d"))
        self.assertContains(response, seller_comment.created_at.strftime("%Y-%m-%d"))

    def test_detail_page_shows_replies_under_parent_and_seller_badge(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="请问支持快递吗？",
        )
        seller_reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="可以快递。",
        )
        buyer_reply = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            parent=parent,
            content="那我考虑一下。",
        )

        response = self.client.get(self.detail_url())

        self.assertContains(response, "请问支持快递吗？")
        self.assertContains(response, "可以快递。")
        self.assertContains(response, "那我考虑一下。")
        self.assertContains(
            response,
            '<span class="comment-seller-badge">卖家</span>',
            count=1,
            html=True,
        )
        self.assertContains(response, seller_reply.created_at.strftime("%Y-%m-%d"))
        self.assertContains(response, buyer_reply.created_at.strftime("%Y-%m-%d"))

    def test_detail_page_shows_empty_comment_state(self):
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "暂无留言，后续咨询会显示在这里。")

    def test_detail_page_handles_deleted_author_and_missing_profile_fields(self):
        self.buyer.profile.nickname = ""
        self.buyer.profile.save(update_fields=["nickname", "updated_at"])
        anonymous_comment = Comment.objects.create(
            listing=self.listing,
            author=self.other_user,
            content="作者即将注销",
        )
        self.other_user.delete()
        anonymous_comment.refresh_from_db()
        Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="昵称为空时展示用户名",
        )

        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "已注销用户")
        self.assertContains(response, self.buyer.username)

    def test_detail_page_escapes_comment_html(self):
        Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content='<script>alert("xss")</script>',
        )

        response = self.client.get(self.detail_url())

        self.assertContains(response, "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;")
        self.assertNotContains(response, '<script>alert("xss")</script>', html=False)

    def test_detail_page_escapes_reply_html_and_preserves_line_breaks(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="顶层留言",
        )
        Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content='<strong>回复</strong>\n<script>alert("xss")</script>',
        )

        response = self.client.get(self.detail_url())

        self.assertContains(response, "&lt;strong&gt;回复&lt;/strong&gt;<br>")
        self.assertContains(response, "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;")
        self.assertNotContains(response, "<strong>回复</strong>", html=False)

    def test_guest_detail_page_shows_login_prompt_without_comment_form(self):
        Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="只读留言",
        )

        response = self.client.get(self.detail_url())

        self.assertContains(response, "登录后留言")
        self.assertNotContains(response, 'class="comment-form"')
        self.assertNotContains(response, "/comments/")
        self.assertNotContains(response, "回复内容")

    def test_logged_in_user_sees_comment_form_on_active_listing(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="欢迎留言",
        )
        self.client.force_login(self.buyer)

        response = self.client.get(self.detail_url())

        self.assertContains(response, "留言内容")
        self.assertContains(response, "发布留言")
        self.assertContains(response, "回复内容")
        self.assertContains(response, reverse("interactions:reply", kwargs={"pk": comment.pk}))
        self.assertContains(
            response,
            reverse("interactions:comment_create", kwargs={"listing_id": self.listing.pk}),
        )

    def test_non_active_listing_hides_comment_form_but_keeps_thread_visible(self):
        reserved = self.create_listing(title="占用商品", status=Listing.Status.RESERVED)
        Comment.objects.create(
            listing=reserved,
            author=self.buyer,
            content="历史留言仍可见",
        )
        self.client.force_login(self.buyer)

        response = self.client.get(self.detail_url(reserved))

        self.assertContains(response, "当前商品暂不支持新增留言，历史留言仍可查看。")
        self.assertContains(response, "历史留言仍可见")
        self.assertNotContains(response, "comment_create")
        self.assertNotContains(response, "回复内容")

    def test_inactive_category_context_closes_interaction_when_owner_can_view(self):
        inactive_category = Category.objects.create(name="前台停用分类", is_active=False)
        hidden_listing = self.create_listing(
            title="停用分类商品",
            category=inactive_category,
            status=Listing.Status.ACTIVE,
        )
        Comment.objects.create(
            listing=hidden_listing,
            author=self.buyer,
            content="停用前历史留言",
        )
        self.client.force_login(self.seller)

        response = self.client.get(self.detail_url(hidden_listing))

        self.assertEqual(response.status_code, 404)

    def test_detail_page_comment_thread_avoids_obvious_n_plus_one(self):
        Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="第一条",
        )
        Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="第二条",
        )
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="第三条",
        )
        Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=parent,
            content="第三条回复",
        )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(captured), 13)
        self.assertContains(response, "第一条")
        self.assertContains(response, "第二条")
        self.assertContains(response, "第三条回复")

    def test_detail_page_keeps_purchase_entry_for_active_listing(self):
        self.client.force_login(self.buyer)

        response = self.client.get(self.detail_url())

        self.assertContains(response, "购买确认")
        self.assertContains(response, f"/listings/{self.listing.pk}/purchase/")

    def test_detail_page_keeps_unavailable_message_for_reserved_sold_and_withdrawn(self):
        reserved = self.create_listing(title="占用商品", status=Listing.Status.RESERVED)
        sold = self.create_listing(title="售出商品", status=Listing.Status.SOLD)
        withdrawn = self.create_listing(title="下架商品", status=Listing.Status.WITHDRAWN)

        reserved_response = self.client.get(self.detail_url(reserved))
        sold_response = self.client.get(self.detail_url(sold))
        self.client.force_login(self.seller)
        withdrawn_response = self.client.get(self.detail_url(withdrawn))

        self.assertContains(reserved_response, "商品正在交易中，暂时无法购买")
        self.assertContains(sold_response, "商品已售出")
        self.assertContains(withdrawn_response, "商品已下架")


class CommentInteractionViewTest(CommentTestMixin, TestCase):
    """留言新增和作者自删视图测试。"""

    def detail_url(self, listing=None):
        listing = listing or self.listing
        return reverse("catalog:listing_detail", kwargs={"pk": listing.pk})

    def create_url(self, listing=None):
        listing = listing or self.listing
        return reverse("interactions:comment_create", kwargs={"listing_id": listing.pk})

    def delete_url(self, comment):
        return reverse("interactions:comment_delete", kwargs={"pk": comment.pk})

    def reply_url(self, comment):
        return reverse("interactions:reply", kwargs={"pk": comment.pk})

    def test_logged_in_user_can_create_comment_for_active_listing(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            self.create_url(),
            {"content": "请问可以今天面交吗？"},
        )

        self.assertRedirects(response, self.detail_url())
        comment = Comment.objects.get()
        self.assertEqual(comment.listing, self.listing)
        self.assertEqual(comment.author, self.buyer)
        self.assertEqual(comment.content, "请问可以今天面交吗？")
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("留言已发布", messages)

    def test_created_comment_is_visible_after_redirect(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            self.create_url(),
            {"content": "页面回跳后可见"},
            follow=True,
        )

        self.assertContains(response, "页面回跳后可见")

    def test_guest_create_comment_requires_login(self):
        response = self.client.post(self.create_url(), {"content": "游客留言"})

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.create_url()}")
        self.assertEqual(Comment.objects.count(), 0)

    def test_blank_comment_is_rejected(self):
        self.client.force_login(self.buyer)

        response = self.client.post(self.create_url(), {"content": "   "})

        self.assertRedirects(response, self.detail_url())
        self.assertEqual(Comment.objects.count(), 0)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("留言内容不能为空", messages)

    def test_oversized_comment_is_rejected(self):
        self.client.force_login(self.buyer)

        response = self.client.post(self.create_url(), {"content": "x" * 1001})

        self.assertRedirects(response, self.detail_url())
        self.assertEqual(Comment.objects.count(), 0)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("留言内容不能超过 1000 个字符", messages)

    def test_non_active_listing_rejects_new_comment(self):
        reserved = self.create_listing(title="不可互动", status=Listing.Status.RESERVED)
        self.client.force_login(self.buyer)

        response = self.client.post(self.create_url(reserved), {"content": "还能买吗"})

        self.assertRedirects(response, self.detail_url(reserved))
        self.assertEqual(Comment.objects.count(), 0)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("该商品目前不能发表评论", messages)

    def test_direct_comment_post_rejects_all_non_interactive_statuses(self):
        statuses = [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]
        self.client.force_login(self.buyer)

        for status in statuses:
            with self.subTest(status=status):
                listing = self.create_listing(title=f"留言关闭 {status}", status=status)

                response = self.client.post(
                    self.create_url(listing),
                    {"content": "不能新增留言"},
                )

                self.assertRedirects(
                    response,
                    self.detail_url(listing),
                    fetch_redirect_response=False,
                )
                self.assertFalse(
                    Comment.objects.filter(
                        listing=listing,
                        content="不能新增留言",
                    ).exists()
                )
                messages = [str(message) for message in get_messages(response.wsgi_request)]
                self.assertIn("该商品目前不能发表评论", messages)

    def test_logged_in_user_can_reply_to_top_level_comment(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="欢迎提问",
        )
        self.client.force_login(self.buyer)

        response = self.client.post(self.reply_url(parent), {"content": "请问还在吗？"})

        self.assertRedirects(response, self.detail_url())
        reply = Comment.objects.get(parent=parent)
        self.assertEqual(reply.listing, self.listing)
        self.assertEqual(reply.author, self.buyer)
        self.assertEqual(reply.content, "请问还在吗？")
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("留言回复成功", messages)

    def test_seller_can_reply_to_top_level_comment(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="买家提问",
        )
        self.client.force_login(self.seller)

        response = self.client.post(self.reply_url(parent), {"content": "卖家答复"})

        self.assertRedirects(response, self.detail_url())
        reply = Comment.objects.get(parent=parent)
        self.assertEqual(reply.author, self.seller)
        self.assertEqual(reply.content, "卖家答复")

    def test_reply_is_visible_after_redirect_under_parent(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="顶层问题",
        )
        self.client.force_login(self.buyer)

        response = self.client.post(
            self.reply_url(parent),
            {"content": "页面回跳后可见的回复"},
            follow=True,
        )

        self.assertContains(response, "顶层问题")
        self.assertContains(response, "页面回跳后可见的回复")

    def test_guest_reply_requires_login(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="顶层留言",
        )

        response = self.client.post(self.reply_url(parent), {"content": "游客回复"})

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.reply_url(parent)}")
        self.assertEqual(Comment.objects.filter(parent__isnull=False).count(), 0)

    def test_blank_and_oversized_reply_are_rejected(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="顶层留言",
        )
        self.client.force_login(self.buyer)

        blank_response = self.client.post(self.reply_url(parent), {"content": "   "})
        oversized_response = self.client.post(
            self.reply_url(parent),
            {"content": "x" * 1001},
        )

        self.assertRedirects(blank_response, self.detail_url())
        self.assertRedirects(oversized_response, self.detail_url())
        self.assertEqual(Comment.objects.filter(parent__isnull=False).count(), 0)
        blank_messages = [str(message) for message in get_messages(blank_response.wsgi_request)]
        oversized_messages = [
            str(message) for message in get_messages(oversized_response.wsgi_request)
        ]
        self.assertIn("留言内容不能为空", blank_messages)
        self.assertIn("留言内容不能超过 1000 个字符", oversized_messages)

    def test_direct_reply_post_rejects_non_interactive_listing(self):
        reserved = self.create_listing(title="回复关闭商品", status=Listing.Status.RESERVED)
        parent = Comment.objects.create(
            listing=reserved,
            author=self.seller,
            content="历史留言",
        )
        self.client.force_login(self.buyer)

        response = self.client.post(self.reply_url(parent), {"content": "不能新增回复"})

        self.assertRedirects(response, self.detail_url(reserved))
        self.assertEqual(Comment.objects.filter(parent=parent).count(), 0)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("该商品目前不能发表评论", messages)

    def test_direct_reply_post_rejects_all_non_interactive_statuses(self):
        statuses = [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]
        self.client.force_login(self.buyer)

        for status in statuses:
            with self.subTest(status=status):
                listing = self.create_listing(title=f"回复关闭 {status}", status=status)
                parent = Comment.objects.create(
                    listing=listing,
                    author=self.seller,
                    content="历史留言",
                )

                response = self.client.post(
                    self.reply_url(parent),
                    {"content": "不能新增回复"},
                )

                self.assertRedirects(
                    response,
                    self.detail_url(listing),
                    fetch_redirect_response=False,
                )
                self.assertFalse(
                    Comment.objects.filter(
                        parent=parent,
                        content="不能新增回复",
                    ).exists()
                )
                messages = [str(message) for message in get_messages(response.wsgi_request)]
                self.assertIn("该商品目前不能发表评论", messages)

    def test_direct_reply_post_rejects_nested_reply(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="顶层留言",
        )
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            parent=parent,
            content="二级回复",
        )
        self.client.force_login(self.other_user)

        response = self.client.post(self.reply_url(reply), {"content": "三级回复"})

        self.assertRedirects(response, self.detail_url())
        self.assertEqual(Comment.objects.filter(parent=reply).count(), 0)
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("不得创建多级留言", messages)

    def test_get_reply_does_not_create_reply(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="顶层留言",
        )
        self.client.force_login(self.buyer)

        response = self.client.get(self.reply_url(parent))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Comment.objects.filter(parent=parent).count(), 0)

    def test_inactive_category_listing_rejects_direct_comment_post(self):
        inactive_category = Category.objects.create(name="停用留言分类", is_active=False)
        hidden_listing = self.create_listing(
            title="隐藏商品",
            category=inactive_category,
            status=Listing.Status.ACTIVE,
        )
        self.client.force_login(self.buyer)

        response = self.client.post(
            self.create_url(hidden_listing),
            {"content": "隐藏商品不应允许留言"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comment.objects.count(), 0)

    def test_create_comment_service_rejects_blank_and_oversized_content(self):
        with self.assertRaisesMessage(ValidationError, "留言内容不能为空"):
            create_comment(self.buyer, self.listing, "   ")
        with self.assertRaisesMessage(ValidationError, "留言内容不能超过 1000 个字符"):
            create_comment(self.buyer, self.listing, "x" * 1001)

        self.assertEqual(Comment.objects.count(), 0)

    def test_create_comment_service_rejects_inactive_category_listing(self):
        inactive_category = Category.objects.create(name="服务层停用分类", is_active=False)
        hidden_listing = self.create_listing(
            title="服务层隐藏商品",
            category=inactive_category,
            status=Listing.Status.ACTIVE,
        )

        with self.assertRaisesMessage(ValidationError, "该商品目前不能发表评论"):
            create_comment(self.buyer, hidden_listing, "不能写入")

        self.assertEqual(Comment.objects.count(), 0)

    def test_create_reply_service_creates_second_level_reply(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="顶层留言",
        )

        reply = create_reply(self.seller, parent, "卖家回复")

        self.assertEqual(reply.listing, self.listing)
        self.assertEqual(reply.author, self.seller)
        self.assertEqual(reply.parent, parent)
        self.assertEqual(reply.content, "卖家回复")

    def test_create_reply_service_allows_non_seller_user(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="卖家顶层留言",
        )

        reply = create_reply(self.buyer, parent, "买家回复")

        self.assertEqual(reply.author, self.buyer)
        self.assertEqual(reply.parent, parent)

    def test_create_reply_service_rejects_guest_blank_oversized_and_nested_reply(self):
        parent = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            content="顶层留言",
        )
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            parent=parent,
            content="二级回复",
        )

        with self.assertRaisesMessage(PermissionDenied, "无权创建评论"):
            create_reply(None, parent, "游客回复")
        with self.assertRaisesMessage(ValidationError, "留言内容不能为空"):
            create_reply(self.buyer, parent, "   ")
        with self.assertRaisesMessage(ValidationError, "留言内容不能超过 1000 个字符"):
            create_reply(self.buyer, parent, "x" * 1001)
        with self.assertRaisesMessage(ValidationError, "不得创建多级留言"):
            create_reply(self.buyer, reply, "三级回复")

        self.assertEqual(Comment.objects.count(), 2)

    def test_create_reply_service_rejects_uninteractive_listing_statuses_and_category(self):
        statuses = [
            Listing.Status.DRAFT,
            Listing.Status.RESERVED,
            Listing.Status.SOLD,
            Listing.Status.WITHDRAWN,
        ]

        for status in statuses:
            with self.subTest(status=status):
                listing = self.create_listing(title=f"不可互动 {status}", status=status)
                parent = Comment.objects.create(
                    listing=listing,
                    author=self.seller,
                    content="历史留言",
                )

                with self.assertRaisesMessage(ValidationError, "该商品目前不能发表评论"):
                    create_reply(self.buyer, parent, "不能回复")

        inactive_category = Category.objects.create(name="回复停用分类", is_active=False)
        hidden_listing = self.create_listing(
            title="停用分类回复商品",
            category=inactive_category,
            status=Listing.Status.ACTIVE,
        )
        parent = Comment.objects.create(
            listing=hidden_listing,
            author=self.seller,
            content="停用分类历史留言",
        )

        with self.assertRaisesMessage(ValidationError, "该商品目前不能发表评论"):
            create_reply(self.buyer, parent, "不能回复")

    def test_author_can_delete_own_comment(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="我要删除的留言",
        )
        self.client.force_login(self.buyer)

        response = self.client.post(self.delete_url(comment))

        self.assertRedirects(response, self.detail_url())
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn("留言已删除", messages)

    def test_deleting_top_level_comment_cascades_its_replies_by_design(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="带回复的顶层留言",
        )
        reply = Comment.objects.create(
            listing=self.listing,
            author=self.seller,
            parent=comment,
            content="依附于顶层留言的回复",
        )
        self.client.force_login(self.buyer)

        response = self.client.post(self.delete_url(comment))

        self.assertRedirects(response, self.detail_url())
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())
        self.assertFalse(Comment.objects.filter(pk=reply.pk).exists())

    def test_non_author_cannot_see_or_delete_comment(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="不能被别人删除",
        )
        self.client.force_login(self.other_user)

        detail_response = self.client.get(self.detail_url())
        delete_response = self.client.post(self.delete_url(comment))

        self.assertNotContains(detail_response, self.delete_url(comment))
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())

    def test_guest_delete_comment_requires_login(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="游客不能删",
        )

        response = self.client.post(self.delete_url(comment))

        self.assertRedirects(response, f"{reverse('users:login')}?next={self.delete_url(comment)}")
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())

    def test_get_delete_does_not_delete_comment(self):
        comment = Comment.objects.create(
            listing=self.listing,
            author=self.buyer,
            content="GET 不能删",
        )
        self.client.force_login(self.buyer)

        response = self.client.get(self.delete_url(comment))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Comment.objects.filter(pk=comment.pk).exists())

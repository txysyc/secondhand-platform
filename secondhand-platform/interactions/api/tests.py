from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.test import APIClient, APITestCase

from catalog.models import Category, Listing
from interactions.models import Comment


User = get_user_model()


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

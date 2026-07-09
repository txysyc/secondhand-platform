"""interactions 应用 pytest 测试。"""

from decimal import Decimal

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Listing
from interactions.admin import CommentAdmin, ReplyStatusFilter
from interactions.models import Comment, ListingFavorite, ListingViewHistory
from interactions.selectors import get_listing_comments


pytestmark = pytest.mark.django_db
User = get_user_model()

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

    def test_favorite_listing_requires_login_and_creates_favorite(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        guest_response = api_client.post(
            reverse(
                "api:listing_favorite",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            )
        )
        user_response = api_client.post(
            reverse(
                "api:listing_favorite",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            **auth_headers(interactions_api_context["buyer"]),
        )
        repeat_response = api_client.post(
            reverse(
                "api:listing_favorite",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            **auth_headers(interactions_api_context["buyer"]),
        )

        assert guest_response.status_code == 401
        assert user_response.status_code == 201
        assert user_response.json()["is_favorited"] is True
        assert repeat_response.status_code == 201
        assert ListingFavorite.objects.count() == 1

    def test_owner_cannot_favorite_own_listing(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        """卖家不能收藏自己发布的商品。"""

        response = api_client.post(
            reverse(
                "api:listing_favorite",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            **auth_headers(interactions_api_context["seller"]),
        )

        assert response.status_code == 403
        assert response.json()["message"] == "不能收藏自己发布的商品"
        assert ListingFavorite.objects.count() == 0

    def test_unfavorite_listing_is_idempotent(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        ListingFavorite.objects.create(
            user=interactions_api_context["buyer"],
            listing=interactions_api_context["listing"],
        )

        first_response = api_client.delete(
            reverse(
                "api:listing_favorite",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            **auth_headers(interactions_api_context["buyer"]),
        )
        second_response = api_client.delete(
            reverse(
                "api:listing_favorite",
                kwargs={"listing_id": interactions_api_context["listing"].id},
            ),
            **auth_headers(interactions_api_context["buyer"]),
        )

        assert first_response.status_code == 204
        assert second_response.status_code == 204
        assert ListingFavorite.objects.count() == 0

    def test_favorite_hidden_listing_returns_404(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        hidden = interactions_api_context["create_listing"](
            status=Listing.Status.DRAFT,
            published_at=None,
        )

        response = api_client.post(
            reverse("api:listing_favorite", kwargs={"listing_id": hidden.id}),
            **auth_headers(interactions_api_context["buyer"]),
        )

        assert response.status_code == 404
        assert ListingFavorite.objects.count() == 0

    def test_my_favorites_returns_paginated_visible_listing(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        hidden = interactions_api_context["create_listing"](
            title="隐藏收藏",
            status=Listing.Status.DRAFT,
            published_at=None,
        )
        favorite = ListingFavorite.objects.create(
            user=interactions_api_context["buyer"],
            listing=interactions_api_context["listing"],
        )
        ListingFavorite.objects.create(
            user=interactions_api_context["buyer"],
            listing=hidden,
        )

        response = api_client.get(
            reverse("api:my_favorites"),
            {"page_size": "999"},
            **auth_headers(interactions_api_context["buyer"]),
        )

        body = response.json()
        assert response.status_code == 200
        assert body["page_size"] == 50
        assert body["count"] == 1
        assert body["results"][0]["id"] == favorite.id
        assert body["results"][0]["listing"]["is_favorited"] is True

    def test_my_browse_history_returns_paginated_visible_listing(
        self,
        api_client,
        auth_headers,
        interactions_api_context,
    ):
        hidden = interactions_api_context["create_listing"](
            title="隐藏历史",
            status=Listing.Status.DRAFT,
            published_at=None,
        )
        history = ListingViewHistory.objects.create(
            user=interactions_api_context["buyer"],
            listing=interactions_api_context["listing"],
        )
        ListingViewHistory.objects.create(
            user=interactions_api_context["buyer"],
            listing=hidden,
        )

        response = api_client.get(
            reverse("api:my_browse_history"),
            **auth_headers(interactions_api_context["buyer"]),
        )

        body = response.json()
        assert response.status_code == 200
        assert body["count"] == 1
        assert body["results"][0]["id"] == history.id
        assert body["results"][0]["listing"]["title"] == interactions_api_context["listing"].title

"""生成可复现的二手交易平台性能测试数据。"""

import json
import uuid
from hashlib import sha256
from datetime import timedelta
from itertools import cycle
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from catalog.cache import (
    clear_active_category_cache,
    invalidate_public_listing_visibility_cache,
)
from catalog.models import Category, Listing
from messaging.models import Conversation, PrivateMessage
from orders.models import Order
from users.models import Profile, User

SCALE_PROFILES = {
    "small": {
        "users": 100,
        "categories": 10,
        "listings": 1000,
        "orders": 500,
        "messages": 2000,
        "write_pool_size": 200,
    },
    "medium": {
        "users": 500,
        "categories": 20,
        "listings": 10000,
        "orders": 5000,
        "messages": 20000,
        "write_pool_size": 200,
    },
    "large": {
        "users": 2000,
        "categories": 30,
        "listings": 50000,
        "orders": 20000,
        "messages": 100000,
        "write_pool_size": 1500,
    },
}


class Command(BaseCommand):
    """创建仅用于 Locust 和查询验证的可控性能数据集。"""

    help = "生成小、中、大三档性能测试数据，只允许在 DEBUG 环境执行。"

    def add_arguments(self, parser):
        """声明数据规模、安全开关和测试账号密码参数。"""

        parser.add_argument("--profile", choices=SCALE_PROFILES, default="medium")
        parser.add_argument("--prefix", default="perf")
        parser.add_argument("--password")
        parser.add_argument("--output-file")
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--confirm-reset", action="store_true")
        parser.add_argument("--cleanup-only", action="store_true")

    def handle(self, *args, **options):
        """校验运行环境后生成或清理指定前缀的性能数据。"""

        if not settings.DEBUG:
            raise CommandError("性能数据命令只能在 DEBUG=True 的专用环境执行")

        prefix = options["prefix"].strip().lower()
        if (
            len(prefix) < 3
            or len(prefix) > 14
            or not prefix.replace("_", "").isalnum()
        ):
            raise CommandError("性能数据前缀为3到14位，且只能包含字母、数字和下划线")
        if (options["reset"] or options["cleanup_only"]) and not options["confirm_reset"]:
            raise CommandError("清理性能数据必须同时传入 --confirm-reset")
        if options["cleanup_only"]:
            self._clear_existing_data(prefix)
            self.stdout.write(self.style.SUCCESS("指定前缀的性能数据已清理。"))
            return
        if not options["password"]:
            raise CommandError("生成性能数据必须提供 --password")
        if self._has_existing_data(prefix) and not options["reset"]:
            raise CommandError("检测到同前缀数据，请更换前缀或使用 --reset --confirm-reset")

        if options["reset"]:
            self._clear_existing_data(prefix)

        profile = SCALE_PROFILES[options["profile"]]
        summary = self._seed_data(prefix, options["password"], profile)
        self.stdout.write(self.style.SUCCESS("性能数据生成完成。"))
        self.stdout.write(f"测试账号邮箱：{summary['buyer_email']}")
        self.stdout.write(f"商品详情 ID：{','.join(map(str, summary['detail_listing_ids']))}")
        self.stdout.write(f"下单商品池：{','.join(map(str, summary['write_listing_ids']))}")
        if options["output_file"]:
            self._write_test_config(options["output_file"], summary)

    def _has_existing_data(self, prefix):
        """通过性能账号邮箱前缀判断目标数据集是否已经存在。"""

        return User.objects.filter(email__startswith=f"{prefix}-").exists()

    def _clear_existing_data(self, prefix):
        """只清理指定前缀创建的订单、用户和分类，避免影响业务数据。"""

        email_prefix = f"{prefix}-"
        with transaction.atomic():
            Order.objects.filter(
                Q(buyer__email__startswith=email_prefix)
                | Q(seller__email__startswith=email_prefix)
            ).delete()
            User.objects.filter(email__startswith=email_prefix).delete()
            Category.objects.filter(name__startswith=f"{prefix}-").delete()
        clear_active_category_cache()
        invalidate_public_listing_visibility_cache()

    def _seed_data(self, prefix, password, profile):
        """批量创建满足商品、订单和私信查询关系的数据集。"""

        now = timezone.now()
        write_pool_size = profile["write_pool_size"]
        username_tag = sha256(prefix.encode("utf-8")).hexdigest()[:5]
        seller_count = profile["users"] // 2
        buyer_count = profile["users"] - seller_count
        password_hash = make_password(password)
        users = []
        for index in range(seller_count):
            users.append(
                User(
                    # 哈希标识同时满足用户名长度限制并避免不同测试批次冲突。
                    username=f"{username_tag}s{index:04d}",
                    email=f"{prefix}-seller-{index:04d}@example.test",
                    password=password_hash,
                    is_active=True,
                )
            )
        for index in range(buyer_count):
            users.append(
                User(
                    # 买家使用相同批次哈希和独立角色标识，确保跨批次唯一。
                    username=f"{username_tag}b{index:04d}",
                    email=f"{prefix}-buyer-{index:04d}@example.test",
                    password=password_hash,
                    is_active=True,
                )
            )

        with transaction.atomic():
            User.objects.bulk_create(users, batch_size=1000)
            created_users = list(
                User.objects.filter(email__startswith=f"{prefix}-").order_by("email")
            )
            Profile.objects.bulk_create(
                [Profile(user=user, nickname=user.username) for user in created_users],
                batch_size=1000,
            )
            sellers = [user for user in created_users if "-seller-" in user.email]
            buyers = [user for user in created_users if "-buyer-" in user.email]
            categories = [
                Category(name=f"{prefix}-分类-{index:02d}")
                for index in range(profile["categories"])
            ]
            Category.objects.bulk_create(categories, batch_size=1000)
            categories = list(Category.objects.filter(name__startswith=f"{prefix}-").order_by("id"))

            listings = []
            seller_cycle = cycle(sellers)
            for index in range(profile["listings"]):
                is_write_pool_listing = index >= profile["listings"] - write_pool_size
                item_type = (
                    Listing.ItemType.VIRTUAL
                    if is_write_pool_listing
                    else Listing.ItemType.PHYSICAL
                )
                listings.append(
                    Listing(
                        owner=next(seller_cycle),
                        category=categories[index % len(categories)],
                        title=f"{prefix}-压测商品-{index:05d}",
                        item_type=item_type,
                        status=(
                            Listing.Status.SOLD
                            if index < profile["orders"]
                            else Listing.Status.ACTIVE
                        ),
                        price="99.00",
                        condition=(Listing.Condition.GOOD if item_type == Listing.ItemType.PHYSICAL else None),
                        description=f"用于关键词搜索的压测商品描述 {index}",
                        delivery_notes="性能测试数据",
                        physical_delivery_method=(
                            Listing.PhysicalDeliveryMethod.MEETUP
                            if item_type == Listing.ItemType.PHYSICAL
                            else None
                        ),
                        virtual_valid_until=(
                            now.date() + timedelta(days=365)
                            if item_type == Listing.ItemType.VIRTUAL
                            else None
                        ),
                        published_at=now - timedelta(minutes=index % 10000),
                    )
                )
            Listing.objects.bulk_create(listings, batch_size=1000)
            created_listings = list(
                Listing.objects.filter(owner__email__startswith=f"{prefix}-").order_by("id")
            )

            buyer_cycle = cycle(buyers)
            orders = []
            for listing in created_listings[: profile["orders"]]:
                buyer = next(buyer_cycle)
                orders.append(
                    Order(
                        buyer=buyer,
                        seller=listing.owner,
                        listing=listing,
                        buyer_display_name=buyer.username,
                        seller_display_name=listing.owner.username,
                        listing_title_snapshot=listing.title,
                        status=Order.OrderStatus.COMPLETED,
                        order_price=listing.price,
                        payment_deadline=now - timedelta(days=2),
                        paid_at=now - timedelta(days=2),
                        shipped_at=now - timedelta(days=1),
                        completed_at=now - timedelta(hours=12),
                    )
                )
            Order.objects.bulk_create(orders, batch_size=1000)

            conversation_pairs = list(zip(sellers[: min(len(sellers), 100)], cycle(buyers)))
            conversations = []
            for seller, buyer in conversation_pairs:
                participant_a, participant_b = sorted([seller, buyer], key=lambda user: user.id)
                conversations.append(
                    Conversation(participant_a=participant_a, participant_b=participant_b)
                )
            Conversation.objects.bulk_create(conversations, batch_size=1000)
            conversations = list(
                Conversation.objects.filter(
                    participant_a__email__startswith=f"{prefix}-"
                ).order_by("id")
            )
            messages = []
            conversation_cycle = cycle(conversations)
            for index in range(profile["messages"]):
                conversation = next(conversation_cycle)
                sender = (
                    conversation.participant_a
                    if index % 2 == 0
                    else conversation.participant_b
                )
                messages.append(
                    PrivateMessage(
                        conversation=conversation,
                        sender=sender,
                        content=f"性能测试私信 {index}",
                    )
                )
            PrivateMessage.objects.bulk_create(messages, batch_size=1000)

        clear_active_category_cache()
        invalidate_public_listing_visibility_cache()
        active_listings = [
            listing
            for listing in created_listings
            if listing.status == Listing.Status.ACTIVE
        ]
        return {
            "buyer_email": buyers[0].email,
            "detail_listing_ids": [listing.id for listing in active_listings[:10]],
            "write_listing_ids": [listing.id for listing in active_listings[-write_pool_size:]],
            "seller_ids": [seller.id for seller in sellers[:50]],
            "buyer_order_accounts": self._serialize_accounts(buyers[:50]),
            "seller_order_accounts": self._serialize_accounts(sellers[:50]),
            "messaging_accounts": self._build_messaging_accounts(buyers, conversations),
            "order_creation_accounts": self._build_order_creation_accounts(
                buyers,
                active_listings[-write_pool_size:],
            ),
        }

    def _serialize_accounts(self, users):
        """为压测账号生成短期 JWT，避免测试启动阶段触发登录接口限流。"""

        return [
            {"user_id": user.id, "access_token": str(RefreshToken.for_user(user).access_token)}
            for user in users
        ]

    def _build_messaging_accounts(self, buyers, conversations):
        """为拥有会话的买家输出账号与可访问会话 ID。"""

        conversation_by_buyer_id = {}
        buyer_ids = {buyer.id for buyer in buyers}
        for conversation in conversations:
            for participant_id in (conversation.participant_a_id, conversation.participant_b_id):
                if participant_id in buyer_ids:
                    conversation_by_buyer_id[participant_id] = conversation.id
        return [
            {
                "user_id": buyer.id,
                "access_token": str(RefreshToken.for_user(buyer).access_token),
                "conversation_id": conversation_by_buyer_id[buyer.id],
            }
            for buyer in buyers
            if buyer.id in conversation_by_buyer_id
        ]

    def _build_order_creation_accounts(self, buyers, listings):
        """为每个创建订单请求分配独立买家、商品和幂等键。"""

        return [
            {
                "user_id": buyer.id,
                "access_token": str(RefreshToken.for_user(buyer).access_token),
                "listing_id": listing.id,
                "idempotency_key": str(uuid.uuid4()),
            }
            for buyer, listing in zip(cycle(buyers), listings)
        ]

    def _write_test_config(self, output_file, summary):
        """把 Locust 所需测试资源写入本次结果目录，避免人工复制环境变量。"""

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.stdout.write(f"压测配置文件：{output_path}")

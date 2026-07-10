"""二手交易平台核心接口 Locust 压测场景。"""

import json
import os
import random
from collections import deque
from pathlib import Path

from locust import HttpUser, between, task
from locust.exception import StopUser

API_PREFIX = "/api/v1"


def _load_test_config():
    """读取一键测试脚本生成的账号、商品与会话配置。"""

    config_file = os.getenv("PERF_CONFIG_FILE")
    if not config_file:
        return {}
    config_path = Path(config_file)
    if not config_path.is_file():
        raise RuntimeError(f"未找到性能测试配置文件：{config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


TEST_CONFIG = _load_test_config()
ORDER_CREATION_REQUESTS = deque(TEST_CONFIG.get("order_creation_accounts", []))
BURST_ORDER_LIMIT = int(os.getenv("PERF_BURST_ORDER_LIMIT", "50"))
BURST_ORDER_REQUESTS = deque(
    TEST_CONFIG.get("order_creation_accounts", [])[:BURST_ORDER_LIMIT]
)


class AccountAllocator:
    """为同类虚拟用户分配独立账号，避免单账号限流和数据热点失真。"""

    def __init__(self, config_key):
        """保存指定场景的可用账号队列。"""

        self.accounts = deque(TEST_CONFIG.get(config_key, []))

    def acquire(self):
        """取出一个未分配账号；账号耗尽时停止当前虚拟用户。"""

        if not self.accounts:
            raise StopUser()
        return self.accounts.popleft()


class ConfiguredUser(HttpUser):
    """使用预生成 JWT 的认证用户基类，不在压测期间请求登录接口。"""

    host = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000")
    account_allocator = None

    def on_start(self):
        """分配账号并配置本虚拟用户的 Bearer Token。"""

        self.account = self.account_allocator.acquire()
        self.client.headers.update(
            {"Authorization": f"Bearer {self.account['access_token']}"}
        )


class AnonymousBrowsingUser(HttpUser):
    """模拟未登录访客浏览公共商品、分类和卖家主页。"""

    host = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000")
    wait_time = between(0.5, 1.5)
    weight = 6

    @task(4)
    def browse_listing_list(self):
        """读取公开商品第一页，覆盖列表序列化与关联预取路径。"""

        self.client.get(f"{API_PREFIX}/listings/?page_size=20", name="商品列表")

    @task(2)
    def search_listing(self):
        """使用性能数据关键词覆盖商品搜索过滤路径。"""

        self.client.get(f"{API_PREFIX}/listings/?q=压测商品&page_size=20", name="商品搜索")

    @task(4)
    def view_listing_detail(self):
        """随机读取热门公开商品详情，覆盖匿名详情缓存命中路径。"""

        listing_ids = TEST_CONFIG.get("detail_listing_ids", [])
        if listing_ids:
            listing_id = random.choice(listing_ids)
            self.client.get(f"{API_PREFIX}/listings/{listing_id}/", name="商品详情")

    @task(1)
    def list_categories(self):
        """读取启用分类，覆盖分类响应缓存路径。"""

        self.client.get(f"{API_PREFIX}/categories/", name="分类列表")

    @task(1)
    def view_seller_profile(self):
        """读取卖家公开主页，覆盖评分摘要聚合读取。"""

        seller_ids = TEST_CONFIG.get("seller_ids", [])
        if seller_ids:
            seller_id = random.choice(seller_ids)
            self.client.get(f"{API_PREFIX}/users/{seller_id}/", name="卖家主页")


class BuyerOrdersUser(ConfiguredUser):
    """模拟拥有历史订单的买家读取订单列表。"""

    wait_time = between(0.8, 2)
    weight = 2
    account_allocator = AccountAllocator("buyer_order_accounts")

    @task
    def buyer_orders(self):
        """读取有数据的买家订单列表及评分预加载字段。"""

        self.client.get(f"{API_PREFIX}/orders/buyer/?page_size=20", name="买家订单列表")


class SellerOrdersUser(ConfiguredUser):
    """模拟拥有历史订单的卖家读取订单列表。"""

    wait_time = between(0.8, 2)
    weight = 2
    account_allocator = AccountAllocator("seller_order_accounts")

    @task
    def seller_orders(self):
        """读取有数据的卖家订单列表，避免空列表掩盖查询成本。"""

        self.client.get(f"{API_PREFIX}/orders/seller/?page_size=20", name="卖家订单列表")


class MessagingUser(ConfiguredUser):
    """模拟进入已有消息的会话并读取消息窗口。"""

    wait_time = between(0.8, 2)
    weight = 1
    account_allocator = AccountAllocator("messaging_accounts")

    @task(2)
    def conversation_list(self):
        """读取当前用户的会话列表。"""

        self.client.get(f"{API_PREFIX}/conversations/?page_size=20", name="私信会话列表")

    @task(3)
    def latest_messages(self):
        """读取会话最新消息窗口，覆盖该接口的 Redis 缓存逻辑。"""

        conversation_id = self.account["conversation_id"]
        self.client.get(
            f"{API_PREFIX}/conversations/{conversation_id}/messages/?limit=20",
            name="私信最新消息",
        )


class OrderCreationUser(HttpUser):
    """固定写入用户持续消费订单池，以稳定覆盖长时间订单创建压力。"""

    host = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000")
    # 50 个用户以约每秒 5 次的速率消费 1,500 个商品，覆盖完整 5 分钟写入测试。
    wait_time = between(8, 12)

    @task
    def create_order(self):
        """从共享商品池取出一组账号和商品，创建订单直到商品池耗尽。"""

        if not ORDER_CREATION_REQUESTS:
            raise StopUser()
        account = ORDER_CREATION_REQUESTS.popleft()
        listing_id = account["listing_id"]
        idempotency_key = account["idempotency_key"]
        with self.client.post(
            f"{API_PREFIX}/listings/{listing_id}/orders/",
            headers={
                "Authorization": f"Bearer {account['access_token']}",
                "Idempotency-Key": idempotency_key,
            },
            name="创建订单",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            else:
                response.failure(f"预期 201，实际 {response.status_code}")


class OrderCreationBurstUser(HttpUser):
    """模拟订单创建突发并发，固定总请求数以观察事务竞争。"""

    host = os.getenv("PERF_BASE_URL", "http://127.0.0.1:8000")

    @task
    def create_order_burst(self):
        """让每个突发用户提交一笔独立订单，商品池耗尽后停止补充请求。"""

        if not BURST_ORDER_REQUESTS:
            raise StopUser()
        account = BURST_ORDER_REQUESTS.popleft()
        with self.client.post(
            f"{API_PREFIX}/listings/{account['listing_id']}/orders/",
            headers={
                "Authorization": f"Bearer {account['access_token']}",
                "Idempotency-Key": account["idempotency_key"],
            },
            name="创建订单（突发并发）",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            else:
                response.failure(f"预期 201，实际 {response.status_code}")
        raise StopUser()

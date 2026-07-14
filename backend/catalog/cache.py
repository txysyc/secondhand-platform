"""catalog 应用的 Redis 缓存读取、失效与降级策略。"""

import logging
import random
from hashlib import sha256
from time import time_ns
from typing import Callable

from django.core.cache import cache
from redis.exceptions import RedisError

from catalog.models import Category

logger = logging.getLogger(__name__)

CACHE_KEY_ACTIVE_CATEGORY_IDS = "catalog:active_category_ids"
CACHE_KEY_ACTIVE_CATEGORY_PAYLOAD = "catalog:active_category_payload"
CACHE_KEY_ACTIVE_CATEGORY_IDS_DIGEST = "catalog:active_category_ids:digest"
CACHE_KEY_ACTIVE_CATEGORY_VERSION = (
    "catalog:active_category:version"  # 版本key，同时其值用于其他缓存作key使用
)
CACHE_KEY_PUBLIC_DETAIL_VERSION = "catalog:public_detail:version"
CACHE_KEY_PUBLIC_DETAIL_LISTING_VERSION = (
    "catalog:public_detail:listing:{listing_id}:version"
)
CACHE_TIMEOUT_NORMAL = 5 * 60
CACHE_TIMEOUT_EMPTY = 30
CACHE_LOCK_TIMEOUT = 5  # 锁超时时间
CACHE_NOT_FOUND_FLAG = "_catalog_cache_not_found"
_CACHE_MISS = object()


def clear_active_category_cache():
    """更新分类版本，使旧分类缓存 key 立即失效。"""

    _bump_active_category_version()


def invalidate_public_listing_detail_cache(listing_id: int):
    """更新单个商品详情缓存版本。"""

    _set_cache_version(_listing_version_key(listing_id))


def invalidate_public_listing_visibility_cache():
    """更新公开商品全局可见性版本。"""

    _bump_public_detail_version()


def get_active_category_ids():
    """读取启用分类 ID 列表，缓存不可用时自动降级查询数据库。"""

    cache_key = _active_category_ids_cache_key()
    digest_key = _active_category_ids_digest_cache_key()
    category_ids = _safe_cache_get(cache_key)
    digest = _safe_cache_get(digest_key)
    # 判断活跃分类id列表是否读取失败和通过该id计算的digest和原来缓存的digest是否一致（即是否活跃分类是否有所改动）
    if category_ids is not _CACHE_MISS and digest == _category_ids_digest(category_ids):
        return category_ids

    # ID 列表与摘要任一缺失或不匹配时，视为缓存不完整并刷新。
    lock_key = f"{cache_key}:lock"
    if _safe_cache_add(lock_key, "building", CACHE_LOCK_TIMEOUT):
        return _refresh_active_category_ids(cache_key, digest_key)
    # 如果重建失败，即有此时并发，所以尝试重新获取
    category_ids = _safe_cache_get(cache_key)
    digest = _safe_cache_get(digest_key)
    if category_ids is not _CACHE_MISS and digest == _category_ids_digest(category_ids):
        return category_ids
    # 读取还是失败，直接访问数据库
    logger.debug("active_category_ids 缓存锁竞争，使用数据库降级读取")
    return _read_active_category_ids()


def get_active_category_payload():
    """读取分类接口需要的轻量字典列表，避免命中后再次查询分类名称。"""

    return _read_cached_value(
        _active_category_payload_cache_key(),
        lambda: list(
            Category.objects.filter(is_active=True).order_by("id").values("id", "name")
        ),
        "active_category_payload",
    )


def get_cached_public_listing_detail(
    listing_id: int,
    builder: Callable[[], dict | None],
):
    """读取匿名公开商品详情快照，不存在时使用短 TTL 空值缓存。"""

    value = _read_cached_value(
        _public_listing_detail_cache_key(listing_id),
        lambda: builder() or {CACHE_NOT_FOUND_FLAG: True},
        "public_listing_detail",
        empty_timeout=True,
    )
    if isinstance(value, dict) and value.get(CACHE_NOT_FOUND_FLAG):
        return None
    return value


def _read_cached_value(cache_key, builder, cache_name, *, empty_timeout=False):
    """按互斥锁读取或构建缓存，锁竞争和 Redis 故障时均可降级数据库。

    ``builder`` 负责从数据库构建缓存值；仅抢到重建锁的请求会回填 Redis。
    未抢到锁的请求会再次读取缓存，仍未命中时直接调用 ``builder`` 返回数据，
    避免等待锁而阻塞 Web 请求。
    """

    # 第一阶段：优先读取已存在的缓存，命中后无需执行数据库查询。
    value = _safe_cache_get(cache_key)
    if value is not _CACHE_MISS:
        return value

    # 第二阶段：缓存未命中时，使用独立锁 Key 选出一个请求负责回源和回填。
    lock_key = f"{cache_key}:lock"
    if _safe_cache_add(lock_key, "building", CACHE_LOCK_TIMEOUT):
        # 当前请求获得锁，由它执行数据库查询，避免并发请求同时回源造成缓存击穿。
        value = builder()
        # 空值缓存使用更短 TTL，正常数据使用默认 TTL；两者均会加入随机抖动。
        timeout = _cache_timeout(
            CACHE_TIMEOUT_EMPTY
            if empty_timeout and _is_empty_value(value)
            else CACHE_TIMEOUT_NORMAL
        )
        # Redis 写入异常已由安全包装函数处理，不影响本次查询得到的数据返回。
        _safe_cache_set(cache_key, value, timeout)
        return value

    # 第三阶段：未获得锁时，构建缓存的请求可能已完成回填，因此再次尝试读取。
    value = _safe_cache_get(cache_key)
    if value is not _CACHE_MISS:
        return value

    # 第四阶段：锁仍被持有或 Redis 故障时，不等待锁，直接查询数据库保证接口可用。
    logger.debug("%s 缓存锁竞争，使用数据库降级读取", cache_name)
    return builder()


def _safe_cache_get(cache_key):
    """读取 Redis 值；连接异常时返回本地未命中标记。"""

    try:
        return cache.get(cache_key, _CACHE_MISS)
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning("Redis 读取失败，已降级数据库查询：%s", exc)
        return _CACHE_MISS


def _safe_cache_add(cache_key, value, timeout):
    """尝试获取缓存重建锁；Redis 异常时让调用方直接回源。"""

    try:
        return cache.add(cache_key, value, timeout=timeout)
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning("Redis 加锁失败，已降级数据库查询：%s", exc)
        return False


def _safe_cache_set(cache_key, value, timeout):
    """写入缓存；写入失败不影响已经生成的业务响应。"""

    try:
        cache.set(cache_key, value, timeout=timeout)
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning("Redis 写入失败，本次响应不使用缓存：%s", exc)


def _is_empty_value(value):
    """判断值是否适合使用短 TTL，商品详情仅空值哨兵采用短期缓存。"""

    return isinstance(value, dict) and value.get(CACHE_NOT_FOUND_FLAG) is True


def _cache_timeout(base_timeout):
    """为缓存过期时间加入固定范围的随机抖动。"""

    jitter = 10 if base_timeout == CACHE_TIMEOUT_EMPTY else 60
    return base_timeout + random.randint(0, jitter)


def _active_category_ids_cache_key():
    """生成启用分类 ID 列表使用的版本化缓存 key。"""

    return f"{CACHE_KEY_ACTIVE_CATEGORY_IDS}:v{_cache_version(CACHE_KEY_ACTIVE_CATEGORY_VERSION)}"


def _active_category_payload_cache_key():
    """生成分类接口响应使用的版本化缓存 key。"""

    return f"{CACHE_KEY_ACTIVE_CATEGORY_PAYLOAD}:v{_cache_version(CACHE_KEY_ACTIVE_CATEGORY_VERSION)}"


def _active_category_ids_digest_cache_key():
    """生成与分类 ID 列表同版本的内容摘要缓存 key。"""

    return f"{CACHE_KEY_ACTIVE_CATEGORY_IDS_DIGEST}:v{_cache_version(CACHE_KEY_ACTIVE_CATEGORY_VERSION)}"


def _public_listing_detail_cache_key(listing_id):
    """生成同时受全局和单商品版本控制的公开详情缓存 key。"""

    global_version = _cache_version(CACHE_KEY_PUBLIC_DETAIL_VERSION)
    listing_version = _cache_version(_listing_version_key(listing_id))
    return f"catalog:public_detail:{listing_id}:v{global_version}:{listing_version}"


def _listing_version_key(listing_id):
    """返回单个商品详情缓存版本的存储 key。"""

    return CACHE_KEY_PUBLIC_DETAIL_LISTING_VERSION.format(listing_id=listing_id)


def _read_active_category_ids():
    """从数据库读取启用分类 ID，并保持稳定排序。"""

    return list(
        Category.objects.filter(is_active=True)
        .order_by("id")
        .values_list("id", flat=True)
    )


def _refresh_active_category_ids(cache_key, digest_key):
    """刷新分类 ID 及其摘要，检测到局部缓存损坏时自动修复。"""

    category_ids = _read_active_category_ids()
    timeout = _cache_timeout(CACHE_TIMEOUT_NORMAL)
    _safe_cache_set(cache_key, category_ids, timeout)
    _safe_cache_set(digest_key, _category_ids_digest(category_ids), timeout)
    return category_ids


def _category_ids_digest(category_ids):
    """计算跨进程稳定的分类 ID 内容摘要。"""

    value = ",".join(str(category_id) for category_id in category_ids or [])
    return sha256(value.encode("ascii")).hexdigest()


def _cache_version(version_key):
    """读取版本号；缓存故障时使用临时版本并让读请求降级。版本号以时间戳做key，返回版本cache key"""

    version = _safe_cache_get(version_key)
    if version is not _CACHE_MISS:
        return version

    version = str(time_ns())
    # 尝试重新创建版本号，如果已有就获取；重新创建成功，直接返回该版本号(由于都是version重新赋予新值，创建失败是由于此时并发的原因)
    if _safe_cache_add(version_key, version, None):
        return version
    # 写入失败通常表示并发请求已先写入版本号，二次读取以统一使用该版本。
    refreshed_version = _safe_cache_get(version_key)
    # Redis 仍不可用时，返回本次生成的临时版本而非未命中标记，保证请求可继续降级执行。
    return refreshed_version if refreshed_version is not _CACHE_MISS else version


def _bump_active_category_version():
    """同步失效分类缓存和依赖分类展示信息的公开商品详情缓存。"""

    _set_cache_version(CACHE_KEY_ACTIVE_CATEGORY_VERSION)
    _bump_public_detail_version()


def _bump_public_detail_version():
    """同步失效受分类可见性影响的公开商品详情缓存。"""

    _set_cache_version(CACHE_KEY_PUBLIC_DETAIL_VERSION)


def _set_cache_version(version_key):
    """写入新版本号，旧 key 由短 TTL 自然回收。"""

    _safe_cache_set(version_key, str(time_ns()), None)

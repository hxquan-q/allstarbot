"""SQL 查询结果缓存

基于项目已有的 FastAPICache / Redis 基础设施，缓存 SQL 查询结果。
由于主查询流程在线程池中同步执行，这里通过 asyncio 桥接异步后端，
所有操作均会在不可用时优雅降级为 no-op，绝不影响主流程。

Key 规范: {prefix}:query:{datasource_id}:{sha256(normalized_sql)}
TTL: 默认 300 秒，可通过 settings.QUERY_CACHE_TTL 配置。
"""
import asyncio
import hashlib
import re
from typing import Any, Optional

import orjson

from common.core.config import settings
from common.core.sqlbot_cache import is_cache_initialized
from common.utils.utils import SQLBotLogUtil

# 缓存命名空间
CACHE_NAMESPACE = "query"

# 默认 TTL（秒）
DEFAULT_TTL = 300


def _normalize_sql(sql: str) -> str:
    """规范化 SQL 用于生成稳定的缓存 key

    - 去除注释
    - 压缩空白
    - 统一小写关键字
    """
    if not sql:
        return ""
    # 去除单行注释
    normalized = re.sub(r"--[^\n]*", "", sql)
    # 去除多行注释
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)
    # 压缩空白
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.lower()


def _build_cache_key(datasource_id: int | str | None, sql: str) -> str:
    """构建缓存 key"""
    norm = _normalize_sql(sql)
    sql_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]
    ds = datasource_id if datasource_id is not None else "default"
    prefix = getattr(settings, "CACHE_PREFIX", "sqlbot-cache") or "sqlbot-cache"
    return f"{prefix}:{CACHE_NAMESPACE}:{ds}:{sql_hash}"


def _get_backend():
    """获取已初始化的缓存后端，未初始化返回 None"""
    if not is_cache_initialized():
        return None
    try:
        from fastapi_cache import FastAPICache
        return FastAPICache.get_backend()
    except Exception:
        return None


def _run_async(coro):
    """在同步上下文中运行异步协程，处理已有事件循环的情况"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 当前线程已有事件循环（不应发生在线程池 worker 中），降级返回 None
        SQLBotLogUtil.debug("Query cache skipped: running inside an event loop")
        return None

    try:
        return asyncio.run(coro)
    except Exception as e:
        SQLBotLogUtil.debug(f"Query cache async run failed: {e}")
        return None


async def _aget(backend, key: str) -> Optional[Any]:
    try:
        raw = await backend.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return orjson.loads(raw)
    except Exception as e:
        SQLBotLogUtil.debug(f"Query cache get failed: {e}")
        return None


async def _aset(backend, key: str, value: Any, ttl: int) -> bool:
    try:
        payload = orjson.dumps(value)
        await backend.set(key, payload, expire=ttl)
        return True
    except Exception as e:
        SQLBotLogUtil.debug(f"Query cache set failed: {e}")
        return False


def get_query_cache(datasource_id: int | str | None, sql: str) -> Optional[dict]:
    """从缓存获取查询结果

    Returns:
        缓存的查询结果 dict，或 None（未命中/不可用）
    """
    backend = _get_backend()
    if backend is None:
        return None

    if not getattr(settings, "QUERY_CACHE_ENABLED", False):
        return None

    key = _build_cache_key(datasource_id, sql)
    return _run_async(_aget(backend, key))


def set_query_cache(datasource_id: int | str | None, sql: str, result: dict) -> bool:
    """写入查询结果到缓存

    Returns:
        是否成功写入
    """
    backend = _get_backend()
    if backend is None:
        return False

    if not getattr(settings, "QUERY_CACHE_ENABLED", False):
        return False

    key = _build_cache_key(datasource_id, sql)
    ttl = getattr(settings, "QUERY_CACHE_TTL", DEFAULT_TTL) or DEFAULT_TTL
    return _run_async(_aset(backend, key, result, ttl)) or False

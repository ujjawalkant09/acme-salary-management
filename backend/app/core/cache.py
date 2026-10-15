"""Read-side cache keyed by the data version.

Every write bumps `app_state.data_version` in its own transaction, so a cached value
built for an older version is simply never looked up again: no stale numbers after an
edit. The TTL only bounds memory.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from cachetools import TTLCache
from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppState

_cache: TTLCache = TTLCache(maxsize=512, ttl=600)


async def get_data_version(db: AsyncSession) -> int:
    state = await db.get(AppState, 1)
    return state.data_version if state else 0


async def bump_data_version(db: AsyncSession) -> None:
    """Call inside the write's transaction, before its commit."""
    await db.execute(
        update(AppState).where(AppState.id == 1).values(data_version=AppState.data_version + 1)
    )


def clear() -> None:
    _cache.clear()


async def get_or_build(
    db: AsyncSession, name: str, params: dict[str, Any], build: Callable[[], Awaitable[Any]]
) -> Any:
    """The value for (name, params) at the current data version, built on a miss."""
    key = (name, _hash(params), await get_data_version(db))
    if key not in _cache:
        _cache[key] = await build()
    return _cache[key]


async def cached_json(
    request: Request,
    response: Response,
    db: AsyncSession,
    name: str,
    params: dict[str, Any],
    build: Callable[[], Awaitable[Any]],
) -> Any:
    """Like `get_or_build` for a JSON response, with an ETag; a matching If-None-Match gets
    an empty 304."""
    etag = f'"v{await get_data_version(db)}-{name}-{_hash(params)}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"

    async def build_json() -> Any:
        return jsonable_encoder(await build())

    return await get_or_build(db, name, params, build_json)


def _hash(params: dict[str, Any]) -> str:
    encoded = json.dumps(params, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]

"""Read-side cache keyed by the data version.

Every write bumps `app_state.data_version` in its own transaction, so a cached value
built for an older version is simply never looked up again: no stale numbers after an
edit. The TTL only bounds memory.
"""

import hashlib
import json
from collections.abc import Callable
from typing import Any

from cachetools import TTLCache
from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import AppState

_cache: TTLCache = TTLCache(maxsize=512, ttl=600)


def get_data_version(db: Session) -> int:
    state = db.get(AppState, 1)
    return state.data_version if state else 0


def bump_data_version(db: Session) -> None:
    """Call inside the write's transaction, before its commit."""
    db.execute(
        update(AppState).where(AppState.id == 1).values(data_version=AppState.data_version + 1)
    )


def clear() -> None:
    _cache.clear()


def get_or_build(db: Session, name: str, params: dict[str, Any], build: Callable[[], Any]) -> Any:
    """The value for (name, params) at the current data version, built on a miss."""
    key = (name, _hash(params), get_data_version(db))
    if key not in _cache:
        _cache[key] = build()
    return _cache[key]


def cached_json(
    request: Request,
    response: Response,
    db: Session,
    name: str,
    params: dict[str, Any],
    build: Callable[[], Any],
) -> Any:
    """Like `get_or_build` for a JSON response, with an ETag; a matching If-None-Match gets
    an empty 304."""
    etag = f'"v{get_data_version(db)}-{name}-{_hash(params)}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"
    return get_or_build(db, name, params, lambda: jsonable_encoder(build()))


def _hash(params: dict[str, Any]) -> str:
    encoded = json.dumps(params, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]

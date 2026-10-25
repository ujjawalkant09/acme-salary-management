"""`Idempotency-Key` support for POSTs that create records or change money.

The key row is added to the session *before* the work runs, so it is committed in the
same transaction as the work: either both are saved or neither is. The response is then
stored on the key in a second commit. A repeat with the same key and body gets the stored
response; the same key with a different body gets 409. If the second commit is lost, a
retry gets 409 "already processed" instead of the stored response: the work still never
runs twice.
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import now
from app.core.errors import Conflict, InvalidInput
from app.models import IdempotencyKey, User

log = logging.getLogger(__name__)

KEY_LIFETIME = timedelta(hours=24)

IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key", max_length=64)]


def request_hash(body: Any) -> str:
    if isinstance(body, BaseModel):
        body = body.model_dump(mode="json")
    encoded = json.dumps(jsonable_encoder(body), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


async def run(
    db: AsyncSession,
    user: User,
    key: str | None,
    endpoint: str,
    body: Any,
    work: Callable[[], Awaitable[Any]],
    status_code: int = 200,
) -> JSONResponse:
    """Run `work` (a service call that commits) at most once per key.

    Without a key the work simply runs.
    """
    if key is None:
        return JSONResponse(jsonable_encoder(await work()), status_code=status_code)
    if not key.strip():
        raise InvalidInput("The Idempotency-Key header must not be empty.")

    body_hash = request_hash(body)
    # Read now: a rollback below expires `user`, and an async session can't reload it.
    user_id = user.id
    existing = await db.get(IdempotencyKey, (key, user_id))
    if existing is not None and existing.expires_at > now():
        return _replay(existing, endpoint, body_hash)
    if existing is not None:
        await db.delete(existing)
        await db.flush()

    record = IdempotencyKey(
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=body_hash,
        expires_at=now() + KEY_LIFETIME,
    )
    db.add(record)
    try:
        result = jsonable_encoder(await work())
    except IntegrityError:
        # Another request with the same key committed first.
        await db.rollback()
        existing = await db.get(IdempotencyKey, (key, user_id))
        if existing is None:
            raise
        return _replay(existing, endpoint, body_hash)

    record.status_code = status_code
    record.response_body = result
    try:
        await db.commit()
    except SQLAlchemyError:
        # The work is already saved; only the stored copy of the response is lost. The
        # caller still gets the real result, and a retry gets 409 "already processed"
        # (never a second change).
        await db.rollback()
        log.warning(
            "could not store the idempotent response", extra={"fields": {"endpoint": endpoint}}
        )
    return JSONResponse(result, status_code=status_code)


def _replay(existing: IdempotencyKey, endpoint: str, body_hash: str) -> JSONResponse:
    if existing.endpoint != endpoint or existing.request_hash != body_hash:
        raise Conflict(
            "This Idempotency-Key was already used for a different request.",
            {"reason": "idempotency_key_reused"},
        )
    if existing.status_code is None:
        raise Conflict(
            "This request was already processed. Reload to see the latest.",
            {"reason": "idempotency_in_progress"},
        )
    return JSONResponse(existing.response_body, status_code=existing.status_code)


async def purge_expired(db: AsyncSession) -> int:
    result = await db.execute(delete(IdempotencyKey).where(IdempotencyKey.expires_at < now()))
    await db.commit()
    return result.rowcount

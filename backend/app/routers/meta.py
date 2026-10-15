from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from app.core import cache
from app.core.auth import DB, CurrentUser
from app.core.config import get_settings
from app.core.rate_limit import READ, limiter
from app.schemas import FxRatesOut, MetaOut
from app.services import meta as service

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health(db: DB):
    """Up check; `commit` tells the as-user oracles which build they are testing."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "commit": get_settings().git_commit}


@router.get("/meta", response_model=MetaOut)
@limiter.limit(READ)
async def meta(request: Request, response: Response, db: DB, _user: CurrentUser):
    return await cache.cached_json(request, response, db, "meta", {}, lambda: service.meta(db))


@router.get("/fx-rates", response_model=FxRatesOut)
@limiter.limit(READ)
async def fx_rates(request: Request, db: DB, _user: CurrentUser):
    return await service.fx_rates(db)
